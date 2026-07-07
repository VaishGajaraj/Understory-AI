"""The three v0 false-alarm filters, in order of cheapness.

1. Persistence — the anomaly recurs across >= 2 consecutive pairs. The single
   most powerful false-alarm cut available at zero model complexity: weather
   decorrelation is transient, a road is not.
2. Spatial clustering — minimum contiguous area; isolated pixels are noise.
3. Geometry — elongation/linearity scoring favoring road- and trail-shaped
   features over diffuse natural blobs.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from pydantic import BaseModel


class FilterConfig(BaseModel):
    min_persistence_pairs: int = 2
    min_cluster_pixels: int = 12
    min_linearity: float = 0.0  # 0 disables the geometry cut; tune on the benchmark


def persistence_filter(candidates: xr.DataArray, min_pairs: int) -> xr.DataArray:
    """Keep pixels anomalous in >= min_pairs consecutive timesteps.

    Implemented as a rolling window along time: a pixel survives at time t if
    every step in [t - min_pairs + 1, t] was a candidate.
    """
    run = candidates.rolling(time=min_pairs, min_periods=min_pairs).sum()
    return (run >= min_pairs).fillna(False)


def cluster_filter(mask: xr.DataArray, min_pixels: int) -> xr.DataArray:
    """Per timestep, drop connected components smaller than min_pixels."""
    raise NotImplementedError("v0: scipy.ndimage.label per timestep, area threshold")


def linearity_score(component_mask: np.ndarray) -> float:
    """Elongation of one connected component in [0, 1].

    Ratio of principal axes from the component's second moments: ~1 for a
    road-like line, ~0 for a compact blob.
    """
    raise NotImplementedError("v0: skimage.measure.regionprops eccentricity/inertia ratio")
