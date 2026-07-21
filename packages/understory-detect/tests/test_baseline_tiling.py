"""Tiling must change peak memory and nothing else.

The whole tiled-baseline change rests on one claim: because the rolling
baseline is per-pixel along time, splitting the grid is exact. If that claim
ever stops holding, these tests fail rather than the science quietly drifting.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from understory_detect.baseline import (
    BaselineConfig,
    anomaly_candidates,
    anomaly_deficit,
    expected_coherence,
)

# Large enough that a small byte budget forces many tiles.
UNTILED = BaselineConfig(max_working_bytes=1 << 60)
TILED = BaselineConfig(max_working_bytes=64 * 1024)


def make_stack(n_time=12, n_y=205, n_x=143, seed=3) -> xr.DataArray:
    """Deliberately non-square, non-power-of-two: tile edges must be handled."""
    rng = np.random.default_rng(seed)
    values = np.clip(0.4 + rng.normal(0, 0.08, size=(n_time, n_y, n_x)), 0, 1).astype(np.float32)
    # Plant a drop so there is real signal, not just noise, to compare.
    values[6:, 20:24, 10:30] = 0.08
    return xr.DataArray(
        values,
        dims=("time", "y", "x"),
        coords={
            "time": np.arange("2026-01-01", n_time * 12, 12, dtype="datetime64[D]").astype(
                "datetime64[ns]"
            ),
            "y": np.linspace(-6.9, -7.0, n_y),
            "x": np.linspace(-55.0, -54.9, n_x),
        },
        name="coherence",
    )


def test_deficit_is_bit_identical_tiled_and_untiled():
    stack = make_stack()
    untiled = anomaly_deficit(stack, UNTILED)
    tiled = anomaly_deficit(stack, TILED)
    assert untiled.attrs["n_tiles"] == 1
    assert tiled.attrs["n_tiles"] > 1
    np.testing.assert_array_equal(untiled.values, tiled.values)


def test_expected_coherence_is_bit_identical_tiled_and_untiled():
    stack = make_stack()
    untiled = expected_coherence(stack, UNTILED)
    tiled = expected_coherence(stack, TILED)
    assert tiled.attrs["n_tiles"] > 1
    for field in ("mean", "spread"):
        np.testing.assert_array_equal(untiled[field].values, tiled[field].values)


def test_candidates_are_identical_tiled_and_untiled():
    stack = make_stack()
    np.testing.assert_array_equal(
        anomaly_candidates(stack, UNTILED).values,
        anomaly_candidates(stack, TILED).values,
    )


@pytest.mark.parametrize("shape", [(9, 1, 1), (9, 1, 200), (9, 200, 1), (5, 3, 3)])
def test_degenerate_shapes_survive_tiling(shape):
    n_time, n_y, n_x = shape
    stack = make_stack(n_time=n_time, n_y=n_y, n_x=n_x)
    tiled = anomaly_deficit(stack, TILED)
    untiled = anomaly_deficit(stack, UNTILED)
    assert tiled.shape == stack.shape
    np.testing.assert_array_equal(tiled.values, untiled.values)


def test_deficit_preserves_coords_and_dtype():
    stack = make_stack()
    deficit = anomaly_deficit(stack, TILED)
    assert deficit.dims == stack.dims
    assert deficit.dtype == stack.dtype
    np.testing.assert_array_equal(deficit["x"].values, stack["x"].values)
    np.testing.assert_array_equal(deficit["y"].values, stack["y"].values)


def test_planted_disturbance_is_still_found_after_tiling():
    """Exactness is not enough — the signal must actually survive."""
    stack = make_stack()
    candidates = anomaly_candidates(stack, TILED)
    # The planted drop is at y 20:24, x 10:30 from step 6 onward.
    assert bool(candidates.isel(time=slice(6, None)).values[:, 20:24, 10:30].any())
