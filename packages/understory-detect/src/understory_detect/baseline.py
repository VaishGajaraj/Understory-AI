"""v0 expected-coherence baseline.

For each pixel, model expected coherence as a rolling robust mean and spread
(median + scaled MAD) over the trailing window — deliberately simple, refined
only where the benchmark shows simplicity failing. A disturbance candidate is
coherence below the expected envelope by a tunable threshold.

Season/land-cover/precipitation conditioning enters when the real-data
benchmark shows the unconditioned baseline failing (tracked in METHODOLOGY.md).
"""

from __future__ import annotations

import xarray as xr
from pydantic import BaseModel

# MAD -> standard deviation under normality.
MAD_SCALE = 1.4826
# Floor on the spread so a freakishly stable history can't turn ordinary
# noise into a 10-sigma anomaly.
MIN_SPREAD = 0.02


class BaselineConfig(BaseModel):
    window_pairs: int = 8  # rolling window length, in 12-day pairs (~3 months)
    min_history_pairs: int = 4  # pixels with less history are not scored
    anomaly_sigma: float = 3.0  # candidate threshold: (expected - observed) / robust std


def expected_coherence(stack: xr.DataArray, config: BaselineConfig) -> xr.Dataset:
    """Per-pixel expected coherence and robust spread.

    Returns a Dataset with ``mean`` and ``spread`` (time, y, x). Each
    timestep's expectation is computed only from *prior* observations — the
    history is shifted by one step so the pair being scored never sees itself.
    Timesteps with fewer than ``min_history_pairs`` prior observations are NaN.
    """
    history = stack.shift(time=1)
    windows = history.rolling(time=config.window_pairs, min_periods=1).construct("window")

    n_valid = windows.notnull().sum("window")
    enough = n_valid >= config.min_history_pairs

    median = windows.median("window", skipna=True).where(enough)
    mad = abs(windows - median).median("window", skipna=True)
    spread = (MAD_SCALE * mad).clip(min=MIN_SPREAD).where(enough)

    return xr.Dataset({"mean": median, "spread": spread})


def anomaly_deficit(stack: xr.DataArray, config: BaselineConfig) -> xr.DataArray:
    """(time, y, x) anomaly depth in robust standard deviations below expectation.

    NaN where there is insufficient history; positive = lower coherence than
    expected.
    """
    expected = expected_coherence(stack, config)
    return (expected["mean"] - stack) / expected["spread"]


def anomaly_candidates(stack: xr.DataArray, config: BaselineConfig) -> xr.DataArray:
    """Boolean (time, y, x): coherence below the expected envelope."""
    return (anomaly_deficit(stack, config) > config.anomaly_sigma).fillna(False)
