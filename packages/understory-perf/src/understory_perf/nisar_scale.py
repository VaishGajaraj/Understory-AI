"""What the real NISAR archive looks like, as numbers the load harness can use.

Every constant here is an observation about the mission or the ASF archive, not
a tuning knob. They are separated from the workload models so that when the
archive changes, one file changes. Sources and observation dates are recorded
in docs/ARCHIVE_STATUS.md; re-derive with ``scripts/probe_archive.py``.

The load harness exists because these numbers are large. A year of 20 m
coherence over a single NISAR frame is ~19 GB, and the detector used to need
~16x its input in working memory. That combination is what decides whether this
project can process one AOI or a hundred.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Orbit and cadence (mission design) ---

REPEAT_CYCLE_DAYS = 12
# 173 tracks per 12-day cycle; a given land point is imaged about twice per
# cycle, once ascending and once descending.
TRACKS_PER_CYCLE = 173
OBSERVATIONS_PER_POINT_PER_CYCLE = 2

# --- Frame geometry (measured from CMR footprint polygons, 2026-07) ---

FRAME_ALONG_TRACK_KM = 245.0
FRAME_CROSS_TRACK_KM = 264.0

# --- GUNW product (ASF, PROVISIONAL tier, measured 2026-07) ---

# The coherence magnitude layer ships at two postings in the same granule. The
# 20 m layer is the one that matters for sub-hectare degradation; the 80 m layer
# is what the unwrapped phase is posted at.
COHERENCE_POSTING_M = {"fine": 20.0, "coarse": 80.0}
GUNW_GRANULE_BYTES = int(1.9e9)
GUNW_GRANULES_PER_DAY = 1116

# Acquisition -> product availability at ASF. The mission requirement is
# 36-72 h; the forward-processing stream measured a median of 105 h during the
# July 2026 ramp-up. The harness uses the observed figure, because a latency
# budget built on the spec would be optimistic by a day and a half.
OBSERVED_PRODUCT_LATENCY_HOURS = 105.0
REQUIREMENT_PRODUCT_LATENCY_HOURS = 72.0

# A ~100 km AOI falls inside 2 frames along-track and is caught by 3-4 distinct
# track/frame combinations because of swath overlap. Each of those is a separate
# stack: geometry cannot be mixed within a coherence time series.
FRAME_GROUPS_PER_AOI = 4
FRAMES_PER_GROUP_PER_AOI = 2


@dataclass(frozen=True)
class FrameGeometry:
    """Raster dimensions of one GUNW frame's coherence layer at a posting."""

    posting_m: float
    height_px: int
    width_px: int

    @property
    def pixels(self) -> int:
        return self.height_px * self.width_px

    def stack_bytes(self, n_pairs: int, itemsize: int = 4) -> int:
        return self.pixels * n_pairs * itemsize


def frame_geometry(posting: str = "fine") -> FrameGeometry:
    """Raster shape of a full NISAR frame at the named coherence posting."""
    if posting not in COHERENCE_POSTING_M:
        raise KeyError(f"unknown posting '{posting}' (known: {sorted(COHERENCE_POSTING_M)})")
    spacing = COHERENCE_POSTING_M[posting]
    return FrameGeometry(
        posting_m=spacing,
        height_px=int(FRAME_ALONG_TRACK_KM * 1000 / spacing),
        width_px=int(FRAME_CROSS_TRACK_KM * 1000 / spacing),
    )


def aoi_geometry(side_km: float, posting: str = "fine") -> FrameGeometry:
    """Raster shape of a square AOI of ``side_km`` at the named posting."""
    spacing = COHERENCE_POSTING_M[posting]
    side_px = int(side_km * 1000 / spacing)
    return FrameGeometry(posting_m=spacing, height_px=side_px, width_px=side_px)


def pairs_per_year(cycles_per_year: float = 365.25 / REPEAT_CYCLE_DAYS) -> int:
    """Single-cycle pairs on one track/frame over a year (~30)."""
    return int(cycles_per_year)
