import numpy as np
import pandas as pd
import pytest
import xarray as xr
from understory_detect.baseline import BaselineConfig, anomaly_candidates, expected_coherence


def stack_from(values: np.ndarray) -> xr.DataArray:
    t, ny, nx = values.shape
    return xr.DataArray(
        values.astype(np.float32),
        dims=("time", "y", "x"),
        coords={
            "time": pd.date_range("2026-01-01", periods=t, freq="12D"),
            "y": np.linspace(0, 1, ny),
            "x": np.linspace(0, 1, nx),
        },
    )


def test_no_leakage_from_scored_pair():
    """A crash at the last timestep must not contaminate its own baseline."""
    values = np.full((6, 1, 1), 0.7)
    values[-1] = 0.1
    stack = stack_from(values)
    expected = expected_coherence(stack, BaselineConfig(min_history_pairs=3))
    assert expected["mean"].values[-1, 0, 0] == pytest.approx(0.7)


def test_insufficient_history_is_not_scored():
    values = np.full((6, 1, 1), 0.1)  # constant low — never anomalous vs itself
    stack = stack_from(values)
    config = BaselineConfig(min_history_pairs=4)
    expected = expected_coherence(stack, config)
    # timesteps 0..3 have 0..3 prior observations -> NaN
    assert np.isnan(expected["mean"].values[:4, 0, 0]).all()
    assert not np.isnan(expected["mean"].values[4:, 0, 0]).any()


def test_drop_is_flagged_and_noise_rarely_is():
    rng = np.random.default_rng(7)
    values = 0.7 + rng.normal(0, 0.05, size=(8, 8, 8))
    values[6:, 1, 1] = 0.15  # sustained crash at one pixel
    stack = stack_from(values)
    candidates = anomaly_candidates(stack, BaselineConfig(min_history_pairs=4))
    assert bool(candidates.values[6, 1, 1])
    assert bool(candidates.values[7, 1, 1])
    # Pure-noise pixels exceed 3 robust sigmas at a small rate (the MAD spread
    # is itself noisy over short histories). Require < 10% before the
    # persistence filter — persistence is what removes the rest.
    noise_candidates = candidates.values.sum() - candidates.values[:, 1, 1].sum()
    scored_steps = candidates.values[4:].size - candidates.values[4:, 1, 1].size
    assert noise_candidates / scored_steps < 0.10


def test_spread_floor_prevents_hypersensitivity():
    """A perfectly constant history must not make 1% dips into anomalies."""
    values = np.full((8, 1, 1), 0.7)
    values[-1] = 0.69
    stack = stack_from(values)
    candidates = anomaly_candidates(stack, BaselineConfig(min_history_pairs=4))
    assert not candidates.values[-1, 0, 0]
