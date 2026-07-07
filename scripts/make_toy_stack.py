"""Generate the miniature synthetic coherence stack for the toy benchmark.

Injects two anomalies into per-pixel noise over 8 timesteps (12-day cadence):
- a persistent linear feature matching label `toy-road-001` (detectable), and
- a transient diffuse blob matching `toy-rain-001` (must be filtered out).

Deterministic (seeded), ~320 KB, regenerated rather than committed. CI runs
this before the toy benchmark so the full pipeline is exercised with no
credentials and no network.

Usage: uv run python scripts/make_toy_stack.py [output.zarr]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# Grid matches benchmarks/toy/aoi.yaml: 5 km x 5 km at ~50 m pixels.
LON_MIN, LON_MAX = -55.025, -54.975
LAT_MIN, LAT_MAX = -7.025, -6.975
N_PIXELS = 100

# Pair-midpoint dates. The road event window (2026-02-01..2026-02-13) covers t5.
TIMES = pd.date_range("2025-12-13", periods=8, freq="12D")

BASE_COHERENCE = 0.70
PIXEL_SIGMA = 0.03  # static per-pixel variation
TEMPORAL_SIGMA = 0.05  # per-observation noise
ROAD_COHERENCE = 0.20
RAIN_COHERENCE = 0.35
ROAD_FROM_STEP = 5  # persistent from here on
RAIN_AT_STEP = 5  # one step only — persistence filter must kill it

DEFAULT_OUT = Path(__file__).parents[1] / "benchmarks" / "toy" / "data" / "toy-stack.zarr"


def _index_of(value: float, lo: float, hi: float) -> int:
    return int(round((value - lo) / (hi - lo) * (N_PIXELS - 1)))


def make_stack() -> xr.Dataset:
    rng = np.random.default_rng(1734)
    lons = np.linspace(LON_MIN, LON_MAX, N_PIXELS)
    lats = np.linspace(LAT_MAX, LAT_MIN, N_PIXELS)  # north-up raster order

    base = BASE_COHERENCE + rng.normal(0, PIXEL_SIGMA, size=(N_PIXELS, N_PIXELS))
    coherence = base[None, :, :] + rng.normal(
        0, TEMPORAL_SIGMA, size=(len(TIMES), N_PIXELS, N_PIXELS)
    )

    # The road: a 2-pixel-wide, ~2 km diagonal line inside the toy-road-001
    # polygon (lon -55.010..-54.990, lat -7.005..-6.995), persistent from
    # ROAD_FROM_STEP.
    x0, x1 = _index_of(-55.010, LON_MIN, LON_MAX), _index_of(-54.990, LON_MIN, LON_MAX)
    y0 = _index_of(-6.995, LAT_MAX, LAT_MIN)
    y1 = _index_of(-7.005, LAT_MAX, LAT_MIN)
    road_xs = np.linspace(x0, x1, num=max(abs(x1 - x0), abs(y1 - y0)) + 1).round().astype(int)
    road_ys = np.linspace(y0, y1, num=len(road_xs)).round().astype(int)
    for t in range(ROAD_FROM_STEP, len(TIMES)):
        for dy in (0, 1):
            coherence[t, road_ys + dy, road_xs] = ROAD_COHERENCE + rng.normal(
                0, 0.03, size=len(road_xs)
            )

    # The rain blob: diffuse, one timestep only, inside toy-rain-001
    # (lon -55.020..-55.015, lat -7.015..-7.010).
    bx0, bx1 = _index_of(-55.020, LON_MIN, LON_MAX), _index_of(-55.015, LON_MIN, LON_MAX)
    by0 = _index_of(-7.010, LAT_MAX, LAT_MIN)
    by1 = _index_of(-7.015, LAT_MAX, LAT_MIN)
    coherence[RAIN_AT_STEP, by0 : by1 + 1, bx0 : bx1 + 1] = RAIN_COHERENCE + rng.normal(
        0, 0.04, size=(by1 - by0 + 1, bx1 - bx0 + 1)
    )

    ds = xr.Dataset(
        {"coherence": (("time", "y", "x"), np.clip(coherence, 0.0, 1.0).astype(np.float32))},
        coords={"time": TIMES, "y": lats, "x": lons},
        attrs={
            "title": "Understory toy coherence stack (synthetic)",
            "crs": "EPSG:4326",
            "generator": "scripts/make_toy_stack.py",
            "seed": 1734,
        },
    )
    return ds


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = make_stack()
    ds.to_zarr(out, mode="w")
    print(f"wrote {out} ({ds.coherence.shape}, {ds.coherence.nbytes / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
