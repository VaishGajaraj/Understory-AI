"""Group surviving anomaly pixels into discrete detection events.

v0 grouping: collapse the filtered mask over time, label 2-D connected
components, and read each component's date range and depth off the time axis.
Components that split or merge across passes are treated as one event — at a
12-day cadence, finer event tracking is more precision than the data supports.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import xarray as xr
from shapely.geometry import MultiPoint, mapping

from understory_detect.filters import label_components, linearity_score

# Anomaly depth (in robust sigmas) at which detector confidence saturates.
SCORE_SATURATION_SIGMA = 10.0


def extract_events(
    surviving: xr.DataArray,
    deficit: xr.DataArray,
    *,
    id_prefix: str,
) -> list[dict]:
    """Return one event dict per spatially connected group of surviving pixels.

    ``surviving``: boolean (time, y, x) after all filters.
    ``deficit``: anomaly depth in sigmas (time, y, x), NaN where unscored.

    Events are plain dicts here; the detector wraps them into ``Detection``
    models (keeps this module free of the interface dependency direction).
    """
    any_mask = surviving.any("time")
    labels, n_components = label_components(any_mask.values)
    if n_components == 0:
        return []

    lons = surviving["x"].values
    lats = surviving["y"].values
    times = surviving["time"].values
    pixel_area_ha = _pixel_area_ha(lons, lats)

    events: list[dict] = []
    for component in range(1, n_components + 1):
        member = labels == component
        ys, xs = np.nonzero(member)

        # Timesteps in which this component has any surviving pixel.
        member_da = xr.DataArray(member, dims=("y", "x"))
        step_hits = surviving.where(member_da, other=False).any(["y", "x"]).values
        hit_indices = np.nonzero(step_hits)[0]

        depths = deficit.values[:, ys, xs][step_hits]
        mean_deficit = float(np.nanmean(depths)) if depths.size else 0.0

        hull = MultiPoint([(lons[x], lats[y]) for y, x in zip(ys, xs, strict=True)]).convex_hull
        # Buffer by half a pixel so single-line features still have area.
        half_pixel = abs(lons[1] - lons[0]) / 2
        geometry = hull.buffer(half_pixel)

        events.append(
            {
                "id": f"{id_prefix}-{component:03d}",
                "geometry": mapping(geometry),
                "first_seen": _to_datetime(times[hit_indices[0]]),
                "last_seen": _to_datetime(times[hit_indices[-1]]),
                "score": float(np.clip(mean_deficit / SCORE_SATURATION_SIGMA, 0.0, 1.0)),
                "persistence_passes": int(len(hit_indices)),
                "area_ha": float(member.sum() * pixel_area_ha),
                "linearity": linearity_score(member),
            }
        )
    return sorted(events, key=lambda e: -e["score"])


def _pixel_area_ha(lons: np.ndarray, lats: np.ndarray) -> float:
    """Approximate pixel area in hectares from lon/lat spacing."""
    mid_lat = math.radians(float(np.mean(lats)))
    dx_m = abs(lons[1] - lons[0]) * 111_320 * math.cos(mid_lat)
    dy_m = abs(lats[1] - lats[0]) * 110_540
    return dx_m * dy_m / 10_000


def _to_datetime(value) -> datetime:
    from typing import cast

    import pandas as pd

    return cast(datetime, pd.Timestamp(value).to_pydatetime())
