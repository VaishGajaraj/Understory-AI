"""Auxiliary masks and joins that constrain and contextualize detection.

- Forest / land-cover mask (ESA WorldCover or similar): restrict the search
  space to forest so agriculture and water never generate candidates.
- Terrain mask (Copernicus DEM): in v0, steep terrain with geometric
  distortion is masked, not modeled.
- Weather join (ERA5 precipitation and wind): natural decorrelation is
  weather-correlated; the baseline model needs to know what the weather was.

v0 takes local rasters / pre-extracted ERA5 tables as inputs so CI and
offline development never depend on live CDS/S3. Fetch instructions live in
docs/DATA_ACCESS.md.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from understory_core.aoi import AreaOfInterest

# ESA WorldCover v200 class 10 = Tree cover.
DEFAULT_FOREST_CLASSES: frozenset[int] = frozenset({10})


def forest_mask(
    aoi: AreaOfInterest,
    grid: xr.DataArray,
    *,
    landcover: xr.DataArray | Path | str,
    forest_classes: frozenset[int] = DEFAULT_FOREST_CLASSES,
) -> xr.DataArray:
    """Boolean (y, x) mask: True where land cover is forest.

    ``landcover`` is an ESA WorldCover (or compatible categorical) raster —
    either an already-opened DataArray or a path to a GeoTIFF. Classes in
    ``forest_classes`` are treated as forest; everything else is False.
    """
    _ = aoi
    lc = _load_raster(landcover, name="landcover")
    sampled = _sample_onto_grid(lc, grid)
    mask = sampled.isin(list(forest_classes))
    return mask.rename("forest").astype(bool)


def terrain_mask(
    aoi: AreaOfInterest,
    grid: xr.DataArray,
    *,
    dem: xr.DataArray | Path | str,
    max_slope_deg: float = 20.0,
) -> xr.DataArray:
    """Boolean (y, x) mask: True where terrain is gentle enough to trust coherence.

    ``dem`` is a Copernicus DEM (or any elevation raster in meters). Slope is
    computed from the DEM, then sampled onto ``grid``. Steep pixels are
    masked rather than corrected in v0.
    """
    _ = aoi
    elevation = _load_raster(dem, name="elevation")
    slope = slope_degrees(elevation)
    sampled = _sample_onto_grid(slope, grid)
    return (sampled <= max_slope_deg).rename("terrain").astype(bool)


def weather_series(
    aoi: AreaOfInterest,
    times: xr.DataArray,
    *,
    era5: xr.Dataset | Path | str | pd.DataFrame,
) -> xr.Dataset:
    """AOI-mean precipitation and wind for each stack timestep (ERA5).

    ``era5`` is a pre-extracted join table — an xarray Dataset / NetCDF with
    dims ``time`` and variables ``precip_mm`` and ``wind_ms``, a CSV with
    columns ``time,precip_mm,wind_ms``, or a pandas DataFrame with the same
    columns. Values are nearest-neighbor matched to each stack midpoint
    within ±6 days (half a repeat cycle); gaps stay NaN.
    """
    _ = aoi  # reserved: future point/area extraction from full ERA5 cubes
    table = _load_weather(era5)
    target = pd.DatetimeIndex(pd.to_datetime(times.values))
    source_times = pd.DatetimeIndex(pd.to_datetime(table["time"].values))

    precip = np.full(len(target), np.nan, dtype=np.float32)
    wind = np.full(len(target), np.nan, dtype=np.float32)
    for i, t in enumerate(target):
        deltas = np.abs((source_times - t).total_seconds())
        j = int(np.argmin(deltas))
        if deltas[j] <= 6 * 24 * 3600:
            precip[i] = float(table["precip_mm"].values[j])
            wind[i] = float(table["wind_ms"].values[j])

    return xr.Dataset(
        {
            "precip_mm": ("time", precip),
            "wind_ms": ("time", wind),
        },
        coords={"time": times.values},
        attrs={"source": "era5-preextracted", "match_tolerance_days": 6},
    )


def slope_degrees(elevation: xr.DataArray) -> xr.DataArray:
    """Compute slope in degrees from a DEM DataArray with spatial dims."""
    elev = _ensure_yx(elevation).astype(np.float64)
    dy_m, dx_m = _pixel_size_meters(elev)
    grad_y, grad_x = np.gradient(elev.values, dy_m, dx_m)
    slope_rad = np.arctan(np.hypot(grad_x, grad_y))
    return xr.DataArray(
        np.degrees(slope_rad).astype(np.float32),
        dims=("y", "x"),
        coords={"y": elev["y"], "x": elev["x"]},
        name="slope_deg",
        attrs=dict(elev.attrs),
    )


def combine_masks(*masks: xr.DataArray) -> xr.DataArray:
    """AND-combine boolean masks onto a shared (y, x) grid."""
    if not masks:
        raise ValueError("combine_masks requires at least one mask")
    out = masks[0].astype(bool)
    for mask in masks[1:]:
        out = out & mask.astype(bool).reindex_like(out, method=None).fillna(False)
    return out.rename("valid")


def _load_raster(source: xr.DataArray | Path | str, *, name: str) -> xr.DataArray:
    if isinstance(source, xr.DataArray):
        da = source
    else:
        try:
            import rioxarray
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("rioxarray is required to load landcover/DEM GeoTIFFs") from e
        opened = rioxarray.open_rasterio(Path(source))
        if isinstance(opened, list):
            raise ValueError(f"expected a single-band raster, got {len(opened)} subdatasets")
        if not isinstance(opened, xr.DataArray):
            raise TypeError(f"expected DataArray from GeoTIFF, got {type(opened).__name__}")
        da = opened.squeeze(drop=True)
        if not isinstance(da, xr.DataArray):
            raise TypeError("squeeze did not yield a DataArray")
    da = _ensure_yx(da)
    da.name = name
    return da


def _ensure_yx(da: xr.DataArray) -> xr.DataArray:
    """Normalize spatial dims to (y, x)."""
    rename: dict[str, str] = {}
    if "latitude" in da.dims:
        rename["latitude"] = "y"
    elif "lat" in da.dims:
        rename["lat"] = "y"
    if "longitude" in da.dims:
        rename["longitude"] = "x"
    elif "lon" in da.dims:
        rename["lon"] = "x"
    if rename:
        da = da.rename(rename)
    if "y" not in da.dims or "x" not in da.dims:
        raise ValueError(f"raster must have spatial dims; got {da.dims}")
    return da


def _load_weather(source: xr.Dataset | Path | str | pd.DataFrame) -> xr.Dataset:
    if isinstance(source, xr.Dataset):
        return _normalize_weather_ds(source)
    if isinstance(source, pd.DataFrame):
        return _normalize_weather_ds(
            xr.Dataset(
                {
                    "precip_mm": ("time", source["precip_mm"].to_numpy(dtype=np.float32)),
                    "wind_ms": ("time", source["wind_ms"].to_numpy(dtype=np.float32)),
                },
                coords={"time": pd.to_datetime(source["time"]).to_numpy()},
            )
        )
    path = Path(source)
    if path.suffix.lower() == ".csv":
        return _load_weather(pd.read_csv(path, parse_dates=["time"]))
    return _normalize_weather_ds(xr.open_dataset(path))


def _normalize_weather_ds(ds: xr.Dataset) -> xr.Dataset:
    if "precip_mm" not in ds or "wind_ms" not in ds:
        raise ValueError("ERA5 join requires variables precip_mm and wind_ms")
    if "time" not in ds.coords and "time" not in ds.variables:
        raise ValueError("ERA5 join requires a time coordinate")
    return ds


def _sample_onto_grid(raster: xr.DataArray, grid: xr.DataArray) -> xr.DataArray:
    """Nearest-neighbor sample ``raster`` onto the (y, x) of ``grid``.

    Geographic source/target pairs use xarray interpolation. Any projected
    source or target uses CRS-aware ``reproject_match``; real GUNW stacks stay
    in their native projected frame CRS through detection.
    """
    sample_grid = grid if set(grid.dims) == {"y", "x"} else grid.isel(time=0)
    raster = _ensure_yx(raster)

    src_crs = _raster_crs(raster)
    if src_crs is None and _coords_look_geographic(raster):
        src_crs = "EPSG:4326"
    target_crs = _raster_crs(sample_grid)
    if target_crs is None and _coords_look_geographic(sample_grid):
        target_crs = "EPSG:4326"

    if src_crs is None or target_crs is None:
        raise ValueError("source and target rasters need a CRS or recognizable lon/lat coordinates")

    src_geographic = src_crs.upper() in ("EPSG:4326", "OGC:CRS84")
    target_geographic = target_crs.upper() in ("EPSG:4326", "OGC:CRS84")
    if src_geographic and target_geographic:
        sampled = raster.interp(x=sample_grid["x"], y=sample_grid["y"], method="nearest")
        return sampled.astype(
            raster.dtype if np.issubdtype(raster.dtype, np.floating) else raster.dtype
        )

    # Any projected grid: build a template in the target CRS and reproject-match.
    try:
        import rioxarray  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("rioxarray is required to sample projected rasters") from e

    template = xr.DataArray(
        np.zeros((sample_grid.sizes["y"], sample_grid.sizes["x"]), dtype=np.float32),
        dims=("y", "x"),
        coords={"y": sample_grid["y"], "x": sample_grid["x"]},
    ).rio.write_crs(target_crs)
    src = raster if _raster_crs(raster) else raster.rio.write_crs(src_crs)
    if not _raster_crs(src):
        src = src.rio.write_crs(src_crs)
    matched = src.rio.reproject_match(template, resampling=_nearest_resampling())
    return xr.DataArray(
        matched.values,
        dims=("y", "x"),
        coords={"y": sample_grid["y"], "x": sample_grid["x"]},
        name=raster.name,
    )


def _nearest_resampling():
    from rasterio.enums import Resampling

    return Resampling.nearest


def _raster_crs(raster: xr.DataArray) -> str | None:
    if hasattr(raster, "rio"):
        try:
            crs = raster.rio.crs
            if crs is not None:
                return crs.to_string()
        except Exception:
            pass
    crs = raster.attrs.get("crs")
    return str(crs) if crs else None


def _coords_look_geographic(da: xr.DataArray) -> bool:
    x = da["x"].values
    y = da["y"].values
    return bool(np.nanmax(np.abs(x)) <= 180 and np.nanmax(np.abs(y)) <= 90)


def _pixel_size_meters(elevation: xr.DataArray) -> tuple[float, float]:
    """Return (dy_m, dx_m) spacing for slope computation."""
    x = elevation["x"].values
    y = elevation["y"].values
    dx = float(np.abs(np.median(np.diff(x))))
    dy = float(np.abs(np.median(np.diff(y))))
    if _coords_look_geographic(elevation):
        mid_lat = math.radians(float(np.mean(y)))
        return dy * 110_540, dx * 111_320 * abs(math.cos(mid_lat))
    return dy, dx
