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
from pydantic import BaseModel, Field
from scipy import ndimage

# 8-connectivity: diagonal pixels belong to the same feature (roads run diagonally).
CONNECTIVITY = np.ones((3, 3), dtype=int)


def label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """8-connected component labeling (typed wrapper over scipy.ndimage.label)."""
    from typing import cast

    return cast(tuple[np.ndarray, int], ndimage.label(mask, structure=CONNECTIVITY))


class FilterConfig(BaseModel):
    # >= 1 enforced: persistence is the single most powerful false-alarm cut
    # available, and a config of 0 would disable it silently rather than loudly.
    min_persistence_pairs: int = Field(default=2, ge=1)
    min_cluster_pixels: int = Field(default=12, ge=1)
    min_linearity: float = 0.0  # 0 disables the geometry cut; tune on the benchmark


def persistence_filter(candidates: xr.DataArray, min_pairs: int) -> xr.DataArray:
    """Keep pixels anomalous in >= min_pairs consecutive timesteps.

    A pixel survives at time t if every step in [t - min_pairs + 1, t] was a
    candidate.

    Done as a chain of shifted ANDs rather than a rolling sum. ``rolling().sum()``
    upcasts the boolean mask to float64 and materializes a (time, y, x, window)
    array, which costs ~16x the mask; over a real frame that was 1.5 GB of
    float64 arithmetic to answer a question about booleans. This holds at most
    two boolean arrays at once and gives identical results.
    """
    if min_pairs < 1:
        raise ValueError(
            f"min_pairs must be >= 1, got {min_pairs} — a non-positive persistence window "
            "would disable the filter rather than widen it"
        )
    if min_pairs == 1:
        # Every candidate survives, but return a copy: the old rolling
        # implementation always produced a fresh array, and aliasing the
        # caller's mask here would let a downstream in-place write reach back
        # into it.
        return candidates.copy()
    surviving = candidates
    for offset in range(1, min_pairs):
        surviving = surviving & candidates.shift(time=offset, fill_value=False)
    return surviving


def cluster_filter(mask: xr.DataArray, min_pixels: int) -> xr.DataArray:
    """Per timestep, drop connected components smaller than min_pixels.

    Loads the mask into memory: connected-component labeling needs whole
    scenes, and a boolean mask is 32x smaller than the coherence stack it came
    from. Real-scale runs parallelize per tile upstream, not here.
    """
    mask = mask.load()

    def _one(step: np.ndarray) -> np.ndarray:
        labels, n = label_components(step)
        if n == 0:
            return np.zeros_like(step, dtype=bool)
        sizes = np.bincount(labels.ravel())
        keep = sizes >= min_pixels
        keep[0] = False  # background
        return keep[labels]

    return xr.apply_ufunc(
        _one,
        mask,
        input_core_dims=[["y", "x"]],
        output_core_dims=[["y", "x"]],
        vectorize=True,
    )


def linearity_score(component_mask: np.ndarray) -> float:
    """Elongation of one connected component in [0, 1].

    From the principal axes of the component's second moments: ~1 for a
    road-like line, ~0 for a compact blob.
    """
    ys, xs = np.nonzero(component_mask)
    if len(ys) < 3:
        return 0.0
    coords = np.stack([ys - ys.mean(), xs - xs.mean()])
    cov = coords @ coords.T / len(ys)
    eigvals = np.sort(np.linalg.eigvalsh(cov))
    major = eigvals[-1]
    if major <= 0:
        return 0.0
    minor = max(eigvals[0], 0.0)
    return float(1.0 - np.sqrt(minor / major))
