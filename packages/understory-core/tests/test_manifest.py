"""Ingest manifest tests: the state store retry and backfill lean on.

All offline — SQLite on a tmp path. The load-bearing property is that a row
means a complete file and survives a killed process, so the "kill" tests reopen
a fresh manifest object (a new process would) and confirm the row is there.
"""

from __future__ import annotations

from datetime import datetime

from understory_core.manifest import GranuleRecord, IngestManifest, utcnow


def make_record(tmp_path, granule_id="G-1", size=None) -> GranuleRecord:
    path = tmp_path / f"{granule_id}.h5"
    path.write_bytes(b"x" * 128)
    return GranuleRecord(
        granule_id=granule_id,
        calibration_tier="beta",
        track=99,
        frame=76,
        reference_start=datetime(2025, 11, 5),
        secondary_start=datetime(2025, 11, 17),
        path=path,
        size_bytes=size if size is not None else path.stat().st_size,
        md5=None,
        checksum_verified=False,
        completed_at=utcnow(),
    )


def test_record_and_get_roundtrip(tmp_path):
    manifest = IngestManifest.for_cache(tmp_path)
    record = make_record(tmp_path)
    manifest.record(record)

    fetched = manifest.get("G-1")
    assert fetched is not None
    assert fetched.granule_id == "G-1"
    assert fetched.track == 99
    assert fetched.path == record.path


def test_row_survives_a_simulated_kill(tmp_path):
    """A row committed by one process must be visible to the next.

    Autocommit means a single INSERT is durable the moment record() returns, so
    a fresh manifest object — standing in for a restarted process — sees it."""
    manifest_path = tmp_path / "ingest-manifest.sqlite"
    IngestManifest(manifest_path).record(make_record(tmp_path))

    reopened = IngestManifest(manifest_path)
    assert reopened.get("G-1") is not None
    assert len(reopened) == 1


def test_intact_is_true_only_when_the_file_matches(tmp_path):
    manifest = IngestManifest.for_cache(tmp_path)
    record = make_record(tmp_path)
    manifest.record(record)

    assert manifest.intact("G-1") == record.path

    # A file truncated after the fact (bad disk, killed writer) is not intact.
    record.path.write_bytes(b"x" * 64)
    assert manifest.intact("G-1") is None


def test_intact_is_none_when_file_is_gone(tmp_path):
    manifest = IngestManifest.for_cache(tmp_path)
    record = make_record(tmp_path)
    manifest.record(record)
    record.path.unlink()
    assert manifest.intact("G-1") is None


def test_intact_is_none_for_unknown_granule(tmp_path):
    manifest = IngestManifest.for_cache(tmp_path)
    assert manifest.intact("never-seen") is None


def test_deep_check_detects_content_corruption(tmp_path):
    """A file the right *size* but the wrong *bytes* passes the cheap check and
    is caught only by the deep re-hash — which is why deep exists."""
    from understory_core.download import _file_md5

    manifest = IngestManifest.for_cache(tmp_path)
    path = tmp_path / "G-1.h5"
    path.write_bytes(b"a" * 128)
    manifest.record(
        GranuleRecord(
            granule_id="G-1",
            calibration_tier="beta",
            track=1,
            frame=2,
            reference_start=datetime(2025, 11, 5),
            secondary_start=datetime(2025, 11, 17),
            path=path,
            size_bytes=128,
            md5=_file_md5(path),
            checksum_verified=True,
            completed_at=utcnow(),
        )
    )
    assert manifest.intact("G-1", deep=True) == path

    # Same length, different content: cheap check passes, deep check fails.
    path.write_bytes(b"b" * 128)
    assert manifest.intact("G-1") == path
    assert manifest.intact("G-1", deep=True) is None


def test_find_pair_by_identity(tmp_path):
    manifest = IngestManifest.for_cache(tmp_path)
    record = make_record(tmp_path)
    manifest.record(record)

    found = manifest.find_pair(
        track=99,
        frame=76,
        calibration_tier="beta",
        reference_start=datetime(2025, 11, 5),
        secondary_start=datetime(2025, 11, 17),
    )
    assert found is not None
    assert found.granule_id == "G-1"

    missing = manifest.find_pair(
        track=99,
        frame=76,
        calibration_tier="beta",
        reference_start=datetime(2020, 1, 1),
        secondary_start=datetime(2020, 1, 13),
    )
    assert missing is None


def test_forget_removes_a_row(tmp_path):
    manifest = IngestManifest.for_cache(tmp_path)
    manifest.record(make_record(tmp_path))
    manifest.forget("G-1")
    assert manifest.get("G-1") is None
    assert len(manifest) == 0
