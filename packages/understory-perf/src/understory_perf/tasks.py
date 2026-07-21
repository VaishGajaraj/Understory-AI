"""The work the load harness actually executes, stage by stage.

These run inside worker processes, so everything here is module-level and
picklable. Each task returns a ``StageTiming`` rather than raising on slowness:
a task that takes ten minutes is a finding, not an error.

The default task synthesizes its coherence stack in memory instead of pulling
real granules. That is a deliberate trade and the reason the harness can be run
as often as you like: a real 24-pair stack over one frame at 20 m posting means
~46 GB of ASF egress and about a day of download, which nobody will re-run per
commit. The synthetic stack has the same shape, dtype and size as the real one,
so it exercises the same memory and compute path — what it cannot tell you is
anything about ASF's throughput, which ``ingest_task`` measures separately
against real granules when credentials are present.
"""

from __future__ import annotations

import resource
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from understory_core.aoi import AreaOfInterest
from understory_core.stack import CoherenceStack
from understory_detect.baseline import BaselineConfig
from understory_detect.detectors import V0Config, V0FilterDetector

from understory_perf.nisar_scale import COHERENCE_POSTING_M
from understory_perf.workload import WorkItem


@dataclass
class StageTiming:
    """One task's outcome: what it did, how long, how much memory, and why not."""

    aoi: str
    frame_group: int
    stage: str
    n_pairs: int
    input_bytes: int
    # Wall-clock (time.time) instants, comparable across processes.
    available_at: float  # when the work became available to the pipeline
    service_start: float  # when a worker actually picked it up
    service_seconds: float
    peak_rss_bytes: int
    n_detections: int = 0
    n_tiles: int = 0
    ok: bool = True
    error: str = ""
    extra: dict = field(default_factory=dict)


def _peak_rss_bytes() -> int:
    """Process peak RSS. macOS reports bytes, Linux kibibytes.

    ru_maxrss is a high-water mark over the whole process lifetime, and
    ProcessPoolExecutor reuses workers -- so after the first item this is the
    largest peak that worker has ever seen, not this item's working set. Read
    per-item values as an upper bound. The run-level figure that the SLO gates
    on comes from the parent's sampler, which does not have this problem.
    """
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def synthetic_stack(item: WorkItem, height_px: int, width_px: int) -> CoherenceStack:
    """A coherence stack with the shape, dtype and statistics of the real thing.

    Base coherence 0.35 with 0.06 spread reflects what L-band repeat-pass
    coherence looks like over closed canopy: low but stable, which is exactly
    why the v0 detector keys on per-pixel deviation rather than an absolute
    threshold. A disturbance is planted so the detector does real work in
    clustering and event extraction rather than returning early on an empty mask.
    """
    rng = np.random.default_rng(item.seed)
    shape = (item.n_pairs, height_px, width_px)
    base = np.float32(0.35) + rng.normal(0, 0.06, size=shape).astype(np.float32)

    # A linear feature across the middle third, present from the halfway pair on.
    onset = item.n_pairs // 2
    y0 = height_px // 2
    length = max(4, width_px // 3)
    x0 = width_px // 3
    base[onset:, y0 : y0 + 2, x0 : x0 + length] = 0.10

    coherence = np.clip(base, 0.0, 1.0)
    times = pd.date_range("2026-01-07", periods=item.n_pairs, freq="12D")
    dataset = xr.Dataset(
        {"coherence": (("time", "y", "x"), coherence)},
        coords={
            "time": times,
            "y": np.linspace(-6.9, -7.0, height_px),
            "x": np.linspace(-55.0, -54.9, width_px),
        },
    )
    aoi = AreaOfInterest(
        name=item.aoi,
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-55.0, -7.0],
                    [-54.9, -7.0],
                    [-54.9, -6.9],
                    [-55.0, -6.9],
                    [-55.0, -7.0],
                ]
            ],
        },
    )
    return CoherenceStack(dataset, aoi)


def detect_task(
    item: WorkItem,
    height_px: int,
    width_px: int,
    max_working_bytes: int,
    available_at: float,
) -> StageTiming:
    """Build a stack of the target geometry and run the v0 detector over it."""
    timing = StageTiming(
        aoi=item.aoi,
        frame_group=item.frame_group,
        stage="detect",
        n_pairs=item.n_pairs,
        input_bytes=item.n_pairs * height_px * width_px * 4,
        available_at=available_at,
        service_start=time.time(),
        service_seconds=0.0,
        peak_rss_bytes=0,
    )
    clock = time.perf_counter()
    try:
        stack = synthetic_stack(item, height_px, width_px)
        detector = V0FilterDetector(
            V0Config(baseline=BaselineConfig(max_working_bytes=max_working_bytes))
        )
        detections = detector.detect(stack)
        timing.n_detections = len(detections)
    except MemoryError as exc:  # the failure mode this harness exists to find
        timing.ok = False
        timing.error = f"MemoryError: {exc}"
    except Exception as exc:  # noqa: BLE001 - a crash under load is a result
        timing.ok = False
        timing.error = f"{type(exc).__name__}: {exc}"
    timing.service_seconds = time.perf_counter() - clock
    timing.peak_rss_bytes = _peak_rss_bytes()
    return timing


def ingest_task(
    item: WorkItem,
    granule_path: str,
    available_at: float,
) -> StageTiming:
    """Read the coherence layer out of a GUNW HDF5 on disk.

    Separate from ``detect_task`` because it measures a different bottleneck:
    HDF5 decompression and disk throughput rather than compute and memory.
    """
    from understory_core.ingest import extract_coherence

    path = Path(granule_path)
    timing = StageTiming(
        aoi=item.aoi,
        frame_group=item.frame_group,
        stage="ingest",
        n_pairs=1,
        input_bytes=path.stat().st_size if path.exists() else 0,
        available_at=available_at,
        service_start=time.time(),
        service_seconds=0.0,
        peak_rss_bytes=0,
    )
    clock = time.perf_counter()
    try:
        raster = extract_coherence(path)
        timing.extra = {"shape": list(raster.shape), "crs": raster.attrs.get("crs", "unknown")}
    except Exception as exc:  # noqa: BLE001
        timing.ok = False
        timing.error = f"{type(exc).__name__}: {exc}"
    timing.service_seconds = time.perf_counter() - clock
    timing.peak_rss_bytes = _peak_rss_bytes()
    return timing


def geometry_for(posting: str, side_km: float) -> tuple[int, int]:
    """Raster height/width for a square AOI at a named coherence posting."""
    spacing = COHERENCE_POSTING_M[posting]
    side_px = max(1, int(side_km * 1000 / spacing))
    return side_px, side_px
