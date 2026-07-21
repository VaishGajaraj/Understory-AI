"""v0 expected-coherence baseline.

For each pixel, model expected coherence as a rolling robust mean and spread
(median + scaled MAD) over the trailing window — deliberately simple, refined
only where the benchmark shows simplicity failing. A disturbance candidate is
coherence below the expected envelope by a tunable threshold.

Season/land-cover/precipitation conditioning enters when the real-data
benchmark shows the unconditioned baseline failing (tracked in METHODOLOGY.md).
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from pydantic import BaseModel
from understory_core.tiling import DEFAULT_TILE_BUDGET_BYTES, tiles_for_budget

# MAD -> standard deviation under normality.
MAD_SCALE = 1.4826
# Floor on the spread so a freakishly stable history can't turn ordinary
# noise into a 10-sigma anomaly.
MIN_SPREAD = 0.02


class BaselineConfig(BaseModel):
    window_pairs: int = 8  # rolling window length, in 12-day pairs (~3 months)
    min_history_pairs: int = 4  # pixels with less history are not scored
    anomaly_sigma: float = 3.0  # candidate threshold: (expected - observed) / robust std
    # Working-memory ceiling for one tile of the rolling baseline. Not a science
    # threshold — it trades peak RSS against per-tile overhead, and is the knob
    # that decides how large an AOI a given machine can process. See
    # docs/PERFORMANCE.md for the measured curve.
    max_working_bytes: int = DEFAULT_TILE_BUDGET_BYTES


def _baseline_slab(slab: xr.DataArray, config: BaselineConfig) -> xr.Dataset:
    """Rolling robust baseline over one spatial slab — the whole memory cost.

    ``construct("window")`` materializes a (time, y, x, window) array and the
    MAD step holds a second one, so this peaks at roughly
    ``2 * window_pairs`` times the slab. Callers reach it through the tiled
    wrappers below, which is what keeps that bounded.
    """
    history = slab.shift(time=1)
    windows = history.rolling(time=config.window_pairs, min_periods=1).construct("window")

    n_valid = windows.notnull().sum("window")
    enough = n_valid >= config.min_history_pairs

    median = windows.median("window", skipna=True).where(enough)
    mad = abs(windows - median).median("window", skipna=True)
    spread = (MAD_SCALE * mad).clip(min=MIN_SPREAD).where(enough)

    return xr.Dataset({"mean": median, "spread": spread})


CANONICAL_DIMS = ("time", "y", "x")


def _tiles(stack: xr.DataArray, config: BaselineConfig):
    """Tile the stack, after checking it is in the order the writer assumes.

    Tiles are *selected* by dimension name but the results are *written back*
    positionally, so a transposed stack would be silently scrambled rather than
    rejected. The whole project's contract is (time, y, x); anything else is a
    caller error worth failing on.
    """
    if tuple(stack.dims) != CANONICAL_DIMS:
        raise ValueError(
            f"expected dims {CANONICAL_DIMS}, got {tuple(stack.dims)} — the tiled baseline "
            "writes results back positionally, so a transposed stack would be silently "
            "scrambled. Call .transpose('time', 'y', 'x') first."
        )
    n_time, n_y, n_x = (stack.sizes["time"], stack.sizes["y"], stack.sizes["x"])
    return tiles_for_budget(
        n_time,
        n_y,
        n_x,
        config.window_pairs,
        budget_bytes=config.max_working_bytes,
        itemsize=stack.dtype.itemsize,
    )


def expected_coherence(stack: xr.DataArray, config: BaselineConfig) -> xr.Dataset:
    """Per-pixel expected coherence and robust spread.

    Returns a Dataset with ``mean`` and ``spread`` (time, y, x). Each
    timestep's expectation is computed only from *prior* observations — the
    history is shifted by one step so the pair being scored never sees itself.
    Timesteps with fewer than ``min_history_pairs`` prior observations are NaN.

    Evaluated tile by tile so peak memory follows ``max_working_bytes`` rather
    than AOI size. The model is per-pixel along time, so tiling is exact: a
    tiled run and a single-tile run return the same values bit for bit.

    The budget is a target, not a guarantee. Deep enough stacks cannot reach it
    without tiles so small that per-tile overhead dominates, and
    ``understory_core.tiling.MIN_TILE_SIDE`` wins in that case with a warning.
    """
    tiles = _tiles(stack, config)
    mean = np.empty(stack.shape, dtype=stack.dtype)
    spread = np.empty(stack.shape, dtype=stack.dtype)
    for tile in tiles:
        window = stack.isel(y=slice(tile.y0, tile.y1), x=slice(tile.x0, tile.x1))
        result = _baseline_slab(window, config)
        mean[:, tile.y0 : tile.y1, tile.x0 : tile.x1] = result["mean"].values
        spread[:, tile.y0 : tile.y1, tile.x0 : tile.x1] = result["spread"].values

    dims, coords = stack.dims, stack.coords
    return xr.Dataset(
        {"mean": (dims, mean), "spread": (dims, spread)},
        coords=coords,
        # Carry the stack's provenance through: calibration_tier and crs are
        # written by CoherenceStack.build and are load-bearing downstream --
        # pre-calibration numbers are never final, and the tier is how a report
        # knows which stream it describes.
        attrs={**stack.attrs, "n_tiles": len(tiles)},
    )


def anomaly_deficit(stack: xr.DataArray, config: BaselineConfig) -> xr.DataArray:
    """(time, y, x) anomaly depth in robust standard deviations below expectation.

    NaN where there is insufficient history; positive = lower coherence than
    expected.

    Tiled like ``expected_coherence``, and one step tighter: the deficit is
    reduced per tile so the full-size mean and spread arrays are never held at
    once. Peak memory is the output plus a single tile's working set.
    """
    tiles = _tiles(stack, config)
    deficit = np.empty(stack.shape, dtype=stack.dtype)
    for tile in tiles:
        window = stack.isel(y=slice(tile.y0, tile.y1), x=slice(tile.x0, tile.x1))
        expected = _baseline_slab(window, config)
        tile_deficit = (expected["mean"] - window) / expected["spread"]
        deficit[:, tile.y0 : tile.y1, tile.x0 : tile.x1] = tile_deficit.values

    return xr.DataArray(
        deficit,
        dims=stack.dims,
        coords=stack.coords,
        name="anomaly_deficit",
        attrs={**stack.attrs, "n_tiles": len(tiles)},
    )


def anomaly_candidates(stack: xr.DataArray, config: BaselineConfig) -> xr.DataArray:
    """Boolean (time, y, x): coherence below the expected envelope."""
    return (anomaly_deficit(stack, config) > config.anomaly_sigma).fillna(False)
