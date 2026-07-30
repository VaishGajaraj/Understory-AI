"""The ingest state store: which granules are on disk, intact, and when.

Retry and backfill need something to be idempotent *against*. Without a record
of what completed, "have I already got this?" can only be answered by looking at
the filesystem — and a file's existence says nothing about whether the process
that wrote it finished.

So a row is written **only after** the fully verified granule has been renamed
into place. The invariant that buys is one-directional and cheap to rely on:

    a row exists  =>  the file it names was complete when the row was written

The converse is deliberately not claimed. A file with no row is *unproven*, not
proven bad, and ``ingest`` decides what to do with it.

SQLite rather than JSON for two reasons that are both about surviving a kill:
a single ``INSERT`` is atomic where a rewritten JSON document is not, and
several fetch workers can write concurrently without a lock file of our own.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

MANIFEST_FILENAME = "ingest-manifest.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS granules (
    granule_id        TEXT PRIMARY KEY,
    calibration_tier  TEXT NOT NULL,
    track             INTEGER NOT NULL,
    frame             INTEGER NOT NULL,
    reference_start   TEXT NOT NULL,
    secondary_start   TEXT NOT NULL,
    path              TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL,
    md5               TEXT,
    checksum_verified INTEGER NOT NULL DEFAULT 0,
    completed_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS granules_by_pair ON granules (
    track, frame, calibration_tier, reference_start, secondary_start
);
"""


class GranuleRecord(BaseModel):
    """One completed granule fetch."""

    granule_id: str
    calibration_tier: str
    track: int
    frame: int
    reference_start: datetime
    secondary_start: datetime
    path: Path
    size_bytes: int
    #: MD5 of the bytes on disk. Present whenever the fetch computed one.
    md5: str | None = None
    #: True only when ``md5`` was compared against a digest published by the
    #: archive. False means the digest describes what we received and nothing
    #: more — useful for detecting later corruption, useless as proof the
    #: transfer was faithful.
    checksum_verified: bool = False
    completed_at: datetime

    model_config = {"frozen": True}


class IngestManifest:
    """A SQLite record of completed granule fetches, kept beside the cache.

    Every method opens and closes its own connection. At the volumes involved —
    one row per ~1.9 GB download — the connection cost is invisible, and it
    keeps the object safe to share across threads without any state of its own.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @classmethod
    def for_cache(cls, cache_dir: Path | str) -> IngestManifest:
        """The manifest belonging to a granule cache directory."""
        return cls(Path(cache_dir) / MANIFEST_FILENAME)

    def record(self, record: GranuleRecord) -> None:
        """Insert or replace the row for one granule."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO granules VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.granule_id,
                    record.calibration_tier,
                    record.track,
                    record.frame,
                    record.reference_start.isoformat(),
                    record.secondary_start.isoformat(),
                    str(record.path),
                    record.size_bytes,
                    record.md5,
                    int(record.checksum_verified),
                    record.completed_at.isoformat(),
                ),
            )

    def get(self, granule_id: str) -> GranuleRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM granules WHERE granule_id = ?", (granule_id,)
            ).fetchone()
        return _to_record(row)

    def find_pair(
        self,
        *,
        track: int,
        frame: int,
        calibration_tier: str,
        reference_start: datetime,
        secondary_start: datetime,
    ) -> GranuleRecord | None:
        """Look a granule up by the tuple a backfill iterates over.

        Backfill plans are expressed as (track, frame, tier, reference,
        secondary) — the same pair identity discovery produces — not as granule
        ids, which nobody holds until after a search.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM granules WHERE track = ? AND frame = ? AND calibration_tier = ? "
                "AND reference_start = ? AND secondary_start = ?",
                (
                    track,
                    frame,
                    calibration_tier,
                    reference_start.isoformat(),
                    secondary_start.isoformat(),
                ),
            ).fetchone()
        return _to_record(row)

    def intact(self, granule_id: str, *, deep: bool = False) -> Path | None:
        """The cached path for ``granule_id``, or None if it is not usable.

        The default check is deliberately cheap — a row plus a matching file
        size — because it runs once per granule per build and re-hashing a
        1.9 GB file to answer "do I need to download this?" would cost more than
        the question is worth. ``deep=True`` re-verifies the recorded MD5 for
        the cases where that trade flips, e.g. auditing a cache after a disk
        scare.
        """
        record = self.get(granule_id)
        if record is None or not record.path.exists():
            return None
        if record.path.stat().st_size != record.size_bytes:
            return None
        if deep and record.md5 is not None:
            from understory_core.download import _file_md5

            if _file_md5(record.path) != record.md5:
                return None
        return record.path

    def forget(self, granule_id: str) -> None:
        """Drop a row, e.g. after deleting a file found to be corrupt."""
        with self._connect() as conn:
            conn.execute("DELETE FROM granules WHERE granule_id = ?", (granule_id,))

    def records(self) -> list[GranuleRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM granules ORDER BY completed_at").fetchall()
        return [record for record in map(_to_record, rows) if record is not None]

    def __len__(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM granules").fetchone()[0])

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # isolation_level=None: autocommit, so a single statement is durable the
        # moment it returns and a killed process cannot lose an uncommitted row.
        # WAL plus a generous busy timeout is what lets concurrent fetch workers
        # write without tripping over each other.
        conn = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            yield conn
        finally:
            conn.close()


def utcnow() -> datetime:
    return datetime.now(UTC)


def _to_record(row: sqlite3.Row | None) -> GranuleRecord | None:
    if row is None:
        return None
    return GranuleRecord(
        granule_id=row["granule_id"],
        calibration_tier=row["calibration_tier"],
        track=row["track"],
        frame=row["frame"],
        reference_start=datetime.fromisoformat(row["reference_start"]),
        secondary_start=datetime.fromisoformat(row["secondary_start"]),
        path=Path(row["path"]),
        size_bytes=row["size_bytes"],
        md5=row["md5"],
        checksum_verified=bool(row["checksum_verified"]),
        completed_at=datetime.fromisoformat(row["completed_at"]),
    )
