"""v0 expected-coherence baseline.

For each pixel (or small superpixel), model expected coherence as a function of
season, land-cover class, and recent precipitation — deliberately simple: a
rolling robust mean and variance per pixel per season, refined only where the
benchmark shows simplicity failing. A disturbance candidate is coherence below
the expected envelope by a tunable threshold.
"""

from __future__ import annotations

import xarray as xr
from pydantic import BaseModel


class BaselineConfig(BaseModel):
    window_pairs: int = 8  # rolling window length, in 12-day pairs (~3 months)
    min_history_pairs: int = 4  # pixels with less history are not scored
    anomaly_sigma: float = 3.0  # candidate threshold: (expected - observed) / robust std


def expected_coherence(stack: xr.DataArray, config: BaselineConfig) -> xr.Dataset:
    """Per-pixel expected coherence and robust spread.

    Returns a Dataset with ``mean`` and ``spread`` (time, y, x), each timestep's
    expectation computed only from *prior* observations — no leakage from the
    pair being scored.
    """
    raise NotImplementedError(
        "v0: rolling median + MAD over the trailing window along time, "
        "shifted by one step so the scored pair never sees itself"
    )


def anomaly_candidates(stack: xr.DataArray, config: BaselineConfig) -> xr.DataArray:
    """Boolean (time, y, x): coherence below the expected envelope."""
    expected = expected_coherence(stack, config)
    deficit = (expected["mean"] - stack) / expected["spread"]
    return deficit > config.anomaly_sigma
