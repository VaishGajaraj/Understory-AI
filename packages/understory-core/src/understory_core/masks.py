"""Auxiliary masks and joins that constrain and contextualize detection.

- Forest / land-cover mask (ESA WorldCover or similar): restrict the search
  space to forest so agriculture and water never generate candidates.
- Terrain mask (Copernicus DEM): in v0, steep terrain with geometric
  distortion is masked, not modeled.
- Weather join (ERA5 precipitation and wind): natural decorrelation is
  weather-correlated; the baseline model needs to know what the weather was.
"""

from __future__ import annotations

import xarray as xr

from understory_core.aoi import AreaOfInterest


def forest_mask(aoi: AreaOfInterest, grid: xr.DataArray) -> xr.DataArray:
    """Boolean (y, x) mask: True where land cover is forest."""
    raise NotImplementedError("v0: rasterize ESA WorldCover tree-cover classes onto the grid")


def terrain_mask(
    aoi: AreaOfInterest, grid: xr.DataArray, max_slope_deg: float = 20.0
) -> xr.DataArray:
    """Boolean (y, x) mask: True where terrain is gentle enough to trust coherence."""
    raise NotImplementedError("v0: slope from Copernicus DEM, threshold")


def weather_series(aoi: AreaOfInterest, times: xr.DataArray) -> xr.Dataset:
    """AOI-mean precipitation and wind for each stack timestep (ERA5)."""
    raise NotImplementedError("v0: ERA5 point/area extraction aligned to pair windows")
