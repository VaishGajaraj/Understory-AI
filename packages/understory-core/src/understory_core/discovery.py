"""NISAR GUNW discovery via the ASF DAAC.

First contact with the archive (July 2026) established the real product model,
which this module encodes:

- One L2 GUNW granule IS one interferometric pair — reference and secondary
  acquisition windows are encoded in the scene name. Pairing happens upstream
  at the NISAR SDS; discovery parses it, it does not construct it.
- Products exist in three calibration tiers: BETA (pre-calibration, the bulk
  of today's archive), PROVISIONAL, and validated V1 (the calibrated Jul 2026+
  stream, filling as the backlog reprocesses). Benchmark results on BETA carry
  the mandatory re-validation caveat from METHODOLOGY.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from understory_core.aoi import AreaOfInterest

# NISAR repeat cycle in days — a hard floor on detection latency.
REPEAT_CYCLE_DAYS = 12

# CMR collection short names per calibration tier.
GUNW_COLLECTIONS = {
    "beta": "NISAR_L2_GUNW_BETA_V1",
    "provisional": "NISAR_L2_GUNW_PROVISIONAL_V1",
    "validated": "NISAR_L2_GUNW_V1",
}

_TIMESTAMP = re.compile(r"\d{8}T\d{6}")


@dataclass(frozen=True)
class GunwPair:
    """One NISAR L2 GUNW granule: a geocoded interferometric pair."""

    granule_id: str
    track: int  # ASF pathNumber
    frame: int
    flight_direction: str  # "ASCENDING" | "DESCENDING"
    reference_start: datetime
    secondary_start: datetime
    url: str  # HTTPS distribution URL
    s3_url: str | None
    calibration_tier: str  # "beta" | "provisional" | "validated"
    # Catalog-reported size and checksum, when CMR carries them. Both feed the
    # integrity check in ingest; both are optional because their presence for
    # NISAR GUNW is not guaranteed (see pair_from_asf_properties).
    size_bytes: int | None = None
    md5: str | None = None

    @property
    def temporal_baseline_days(self) -> int:
        return (self.secondary_start - self.reference_start).days

    @property
    def frame_key(self) -> tuple[int, int, str]:
        return (self.track, self.frame, self.flight_direction)

    @property
    def midpoint(self) -> datetime:
        return self.reference_start + (self.secondary_start - self.reference_start) / 2


def parse_pair_times(scene_name: str) -> tuple[datetime, datetime]:
    """Reference and secondary acquisition start times from a GUNW scene name.

    Names carry four timestamps: reference start/end, secondary start/end, e.g.
    NISAR_L2_PR_GUNW_009_155_D_094_010_2000_SH_20260107T231703_20260107T231737_
    20260119T231703_20260119T231738_X05010_N_P_J_001
    """
    stamps = _TIMESTAMP.findall(scene_name)
    if len(stamps) < 4:
        raise ValueError(
            f"expected 4 timestamps in GUNW scene name, got {len(stamps)}: {scene_name}"
        )
    fmt = "%Y%m%dT%H%M%S"
    return datetime.strptime(stamps[0], fmt), datetime.strptime(stamps[2], fmt)


def pair_from_asf_properties(properties: dict, tier: str) -> GunwPair:
    """Build a GunwPair from an asf_search result's ``properties`` dict."""
    scene = properties["sceneName"]
    reference_start, secondary_start = parse_pair_times(scene)
    s3_urls = [u for u in properties.get("s3Urls") or [] if u.endswith(".h5")]
    return GunwPair(
        granule_id=scene,
        track=int(properties["pathNumber"]),
        frame=int(properties["frameNumber"]),
        flight_direction=str(properties.get("flightDirection", "")).upper(),
        reference_start=reference_start,
        secondary_start=secondary_start,
        url=properties.get("url", ""),
        s3_url=s3_urls[0] if s3_urls else None,
        calibration_tier=tier,
        size_bytes=_h5_size_bytes(properties),
        md5=_md5sum(properties),
    )


def _h5_size_bytes(properties: dict) -> int | None:
    """Bytes of the granule's HDF5 file from the CMR record, if reported.

    asf_search's NISARProduct exposes ``bytes`` as ``{filename: {'bytes': int,
    ...}}`` (one entry per distributed file); the generic path leaves it an int.
    Both are tolerated, and anything unexpected yields None rather than raising —
    a missing size just means the length check falls back to Content-Length.
    """
    raw = properties.get("bytes")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, dict):
        h5 = [v for name, v in raw.items() if name.endswith(".h5")]
        entry = (h5 or list(raw.values()))[0] if raw else None
        if isinstance(entry, dict) and isinstance(entry.get("bytes"), int):
            return entry["bytes"]
    return None


def _md5sum(properties: dict) -> str | None:
    """The catalog MD5 for the granule's HDF5, when the record carries one.

    Settled against the live archive (2026-07-27): CMR **does** publish an MD5
    per distributed file for NISAR GUNW, in each ``ArchiveAndDistributionInfo``
    entry's ``Checksum``. asf_search's flat ``md5sum`` property is nonetheless
    ``None`` for these granules — it is not wired to that field — so reading
    only ``md5sum`` silently gives up a digest the archive actually publishes,
    and every download degrades to the honest-but-weaker "fingerprint, not
    verification" path.

    So both are tried: the flat property first, then the per-file checksum from
    the UMM record under whichever key asf_search surfaced it. Anything
    unexpected yields None rather than raising — a missing digest is a weaker
    guarantee, not an error.
    """
    value = properties.get("md5sum")
    if isinstance(value, str) and value:
        return value

    for key in ("archiveAndDistributionInformation", "ArchiveAndDistributionInformation"):
        entries = properties.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not str(entry.get("Name", "")).endswith(".h5"):
                continue
            checksum = entry.get("Checksum")
            if isinstance(checksum, dict) and str(checksum.get("Algorithm", "")).upper() == "MD5":
                digest = checksum.get("Value")
                if isinstance(digest, str) and digest:
                    return digest
    return None


def search_gunw_pairs(
    aoi: AreaOfInterest,
    start: date,
    end: date,
    tier: str = "beta",
    max_results: int | None = None,
) -> list[GunwPair]:
    """Search ASF for GUNW pairs intersecting the AOI in the date window.

    Searching needs no credentials; retrieval does (see docs/DATA_ACCESS.md).
    """
    import asf_search as asf

    if tier not in GUNW_COLLECTIONS:
        raise KeyError(f"unknown calibration tier '{tier}' (known: {sorted(GUNW_COLLECTIONS)})")
    # asf_search.search is a function shadowing a submodule of the same name,
    # which the type checker resolves to the module; getattr sidesteps that.
    search_fn = getattr(asf, "search")  # noqa: B009
    results = search_fn(
        shortName=GUNW_COLLECTIONS[tier],
        intersectsWith=aoi.wkt,
        start=start.isoformat(),
        end=end.isoformat(),
        maxResults=max_results,
    )
    pairs = [pair_from_asf_properties(r.properties, tier) for r in results]
    return sorted(pairs, key=lambda p: (p.frame_key, p.reference_start))


def group_by_frame(pairs: list[GunwPair]) -> dict[tuple[int, int, str], list[GunwPair]]:
    """Group pairs by (track, frame, direction), time-ordered within each frame.

    A coherence stack is built per frame group; mixing geometries corrupts the
    per-pixel time series.
    """
    grouped: dict[tuple[int, int, str], list[GunwPair]] = {}
    for pair in sorted(pairs, key=lambda p: p.reference_start):
        grouped.setdefault(pair.frame_key, []).append(pair)
    return grouped


def single_cycle_pairs(pairs: list[GunwPair]) -> list[GunwPair]:
    """Keep only pairs at exactly one repeat cycle (12 days).

    Longer temporal baselines decorrelate too heavily in forest to be usable
    in the v0 time series.
    """
    return [p for p in pairs if p.temporal_baseline_days == REPEAT_CYCLE_DAYS]
