"""NISAR granule discovery via the ASF DAAC.

Finds Level-2 interferometric products covering an AOI and pairs consecutive
passes on the 12-day repeat cycle. Discovery returns lightweight references;
retrieval is ingest's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from understory_core.aoi import AreaOfInterest

# NISAR repeat cycle in days — a hard floor on detection latency.
REPEAT_CYCLE_DAYS = 12


@dataclass(frozen=True)
class GranuleRef:
    """A reference to one NISAR L2 granule at ASF (not yet retrieved)."""

    granule_id: str
    track: int
    frame: int
    acquisition: datetime
    product_type: str  # e.g. "GUNW" (geocoded unwrapped interferogram) / "GCOV"
    url: str  # S3 or HTTPS location


@dataclass(frozen=True)
class InterferometricPair:
    """A consecutive-pass pair from which one coherence raster derives."""

    reference: GranuleRef
    secondary: GranuleRef

    @property
    def temporal_baseline_days(self) -> int:
        return (self.secondary.acquisition - self.reference.acquisition).days


def search_granules(
    aoi: AreaOfInterest,
    start: date,
    end: date,
    product_type: str = "GUNW",
) -> list[GranuleRef]:
    """Search ASF for NISAR granules covering the AOI in the date window.

    Wraps ``asf_search``; requires Earthdata credentials for retrieval but not
    for search itself.
    """
    raise NotImplementedError(
        "v0: wrap asf_search.geo_search(platform='NISAR', intersectsWith=aoi.wkt, ...)"
    )


def pair_consecutive_passes(granules: list[GranuleRef]) -> list[InterferometricPair]:
    """Group granules by (track, frame) and pair consecutive acquisitions.

    Only pairs at exactly one repeat cycle (12 days) are kept for the v0
    coherence time series; longer baselines decorrelate too much in forest.
    """
    pairs: list[InterferometricPair] = []
    by_frame: dict[tuple[int, int], list[GranuleRef]] = {}
    for g in granules:
        by_frame.setdefault((g.track, g.frame), []).append(g)
    for frame_granules in by_frame.values():
        ordered = sorted(frame_granules, key=lambda g: g.acquisition)
        for ref, sec in zip(ordered, ordered[1:], strict=False):
            pair = InterferometricPair(reference=ref, secondary=sec)
            if pair.temporal_baseline_days == REPEAT_CYCLE_DAYS:
                pairs.append(pair)
    return pairs
