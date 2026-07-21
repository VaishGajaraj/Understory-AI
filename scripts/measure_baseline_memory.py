"""Measure the rolling baseline's real peak memory, per slab byte.

``understory_core.tiling.BASELINE_MEMORY_FACTOR`` decides how large a tile the
detector will attempt, and therefore how large an AOI fits on a given machine.
Reasoning from the source gives 2; measuring gives ~9, because nanmedian sorts
a copy, the validity count is another window-sized array, and freed blocks stay
in the allocator's arenas rather than returning to the OS.

Since the number the OOM killer sees is the one that matters, the constant is
calibrated here rather than derived. Re-run after changing baseline.py.

Usage: uv run python scripts/measure_baseline_memory.py
"""

from __future__ import annotations

import subprocess
import sys

from understory_core.tiling import BASELINE_MEMORY_FACTOR

# (n_time, side) slab shapes. Deliberately varied in both depth and area so a
# factor that only holds at one aspect ratio shows up as scatter.
SHAPES = [(24, 400), (24, 600), (24, 800), (12, 800), (36, 500)]

# Each slab is measured in a fresh process: ru_maxrss is a high-water mark that
# never decreases, so successive measurements in one process are meaningless.
CHILD = """
import resource, sys, warnings
import numpy as np, xarray as xr
from understory_detect.baseline import BaselineConfig, _baseline_slab

n_time, side = {n_time}, {side}
values = np.clip(
    0.4 + np.random.default_rng(1).normal(0, 0.05, size=(n_time, side, side)), 0, 1
).astype(np.float32)
slab = xr.DataArray(
    values,
    dims=("time", "y", "x"),
    coords={{
        "time": np.arange("2026-01-01", n_time * 12, 12, dtype="datetime64[D]").astype(
            "datetime64[ns]"
        ),
        "y": np.arange(side),
        "x": np.arange(side),
    }},
)
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    _baseline_slab(slab, BaselineConfig())
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
scale = 1 if sys.platform == "darwin" else 1024
print((after - before) * scale, values.nbytes)
"""

WINDOW_PAIRS = 8  # BaselineConfig default, which the child uses


def main() -> int:
    print(f"{'slab':>18} {'slab_MB':>9} {'peak_MB':>9} {'factor':>8}")
    factors: list[float] = []
    for n_time, side in SHAPES:
        result = subprocess.run(
            [sys.executable, "-c", CHILD.format(n_time=n_time, side=side)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  {n_time}x{side}^2 FAILED:\n{result.stderr[-500:]}", file=sys.stderr)
            return 1
        delta_bytes, slab_bytes = (int(v) for v in result.stdout.split())
        factor = delta_bytes / slab_bytes / WINDOW_PAIRS
        factors.append(factor)
        print(
            f"{n_time}x{side}x{side:>5} {slab_bytes / 1e6:9.1f} "
            f"{delta_bytes / 1e6:9.1f} {factor:8.2f}"
        )

    worst = max(factors)
    print(f"\nmeasured factor: min {min(factors):.2f}, max {worst:.2f}")
    print(f"BASELINE_MEMORY_FACTOR is currently {BASELINE_MEMORY_FACTOR}")
    if worst > BASELINE_MEMORY_FACTOR:
        print(
            f"\nUNDER-BUDGETED: measured {worst:.2f} exceeds the configured "
            f"{BASELINE_MEMORY_FACTOR}. Tiles will be larger than the budget allows and "
            "runs will OOM. Raise the constant in understory_core/tiling.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
