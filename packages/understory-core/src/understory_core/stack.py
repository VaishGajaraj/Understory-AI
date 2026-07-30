"""Coherence time-series stack construction.

A CoherenceStack is the central data structure of the whole project: a
per-pixel time series of 12-day coherence values over an AOI, stored as a
Zarr-backed xarray Dataset with dims (time, y, x). Everything downstream —
baselines, detectors, scoring — consumes this.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.ingest import extract_coherence

logger = logging.getLogger(__name__)


class CoherenceStack:
    """Zarr-backed per-pixel coherence time series over one AOI."""

    def __init__(self, dataset: xr.Dataset, aoi: AreaOfInterest):
        self.dataset = dataset
        self.aoi = aoi

    @property
    def coherence(self) -> xr.DataArray:
        """(time, y, x) coherence values, float32 in [0, 1]."""
        return self.dataset["coherence"]

    @property
    def valid(self) -> xr.DataArray | None:
        """Optional (y, x) boolean mask of pixels trusted for detection.

        Present when forest/terrain masks were joined at build time or via
        ``with_valid_mask``. Detectors skip pixels where this is False.
        """
        if "valid" in self.dataset:
            return self.dataset["valid"]
        return None

    @property
    def crs(self) -> str:
        """Canonical CRS of the raster grid."""
        crs = str(self.dataset.attrs.get("crs", self.coherence.attrs.get("crs", "unknown")))
        if crs == "unknown" and _coords_look_geographic(self.coherence):
            return "EPSG:4326"
        return crs

    def with_valid_mask(self, mask: xr.DataArray) -> CoherenceStack:
        """Return a copy carrying a (y, x) validity mask aligned to the grid."""
        aligned = mask.astype(bool)
        if set(aligned.dims) != {"y", "x"}:
            raise ValueError(f"valid mask must be (y, x); got dims {aligned.dims}")
        aligned = aligned.reindex_like(self.coherence.isel(time=0), method=None)
        ds = self.dataset.copy()
        ds["valid"] = aligned.fillna(False)
        return CoherenceStack(ds, self.aoi)

    @classmethod
    def build(
        cls,
        aoi: AreaOfInterest,
        pairs: list[GunwPair],
        store: Path | str,
        *,
        cache_dir: Path | str | None = None,
        resolution_m: int = 20,
        polarization: str = "HH",
        frequency: str = "frequencyA",
    ) -> CoherenceStack:
        """Extract coherence for each pair, clip to the AOI, align on a common
        grid, and stack along time (indexed by pair midpoint date).

        ``pairs`` must come from a single frame group (see
        ``discovery.group_by_frame``) — mixing geometries corrupts the
        per-pixel time series.
        """
        if not pairs:
            raise ValueError("CoherenceStack.build requires at least one GUNW pair")

        frame_keys = {p.frame_key for p in pairs}
        if len(frame_keys) > 1:
            raise ValueError(
                f"pairs span {len(frame_keys)} frame groups {sorted(frame_keys)}; "
                "build one stack per frame group (see discovery.group_by_frame)"
            )

        cache = Path(cache_dir) if cache_dir else Path("data/scratch/granules")
        ordered = sorted(pairs, key=lambda p: p.midpoint)
        layers: list[xr.DataArray] = []
        for pair in ordered:
            logger.info("extracting %s", pair.granule_id)
            da = extract_coherence(
                pair,
                cache_dir=cache,
                resolution_m=resolution_m,
                polarization=polarization,
                frequency=frequency,
            )
            clipped = _clip_to_aoi(da, aoi)
            timed = clipped.expand_dims(time=[pd.Timestamp(pair.midpoint)])
            timed.attrs.update(clipped.attrs)
            layers.append(timed)

        reference = layers[0]
        aligned = [reference] + [_match_grid(layer, reference) for layer in layers[1:]]
        stacked = xr.concat(aligned, dim="time").sortby("time").astype(np.float32)
        stacked.name = "coherence"

        tiers = sorted({p.calibration_tier for p in ordered})
        ds = stacked.to_dataset(name="coherence")
        ds.attrs.update(
            {
                "aoi": aoi.name,
                "track": ordered[0].track,
                "frame": ordered[0].frame,
                "flight_direction": ordered[0].flight_direction,
                "calibration_tiers": ",".join(tiers),
                "n_pairs": len(ordered),
                "crs": reference.attrs.get("crs", "unknown"),
                "resolution_m": resolution_m,
                "polarization": polarization.upper(),
                "frequency": frequency,
                "granule_ids": [pair.granule_id for pair in ordered],
            }
        )

        store_path = Path(store)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        ds.to_zarr(store_path, mode="w")
        return cls(xr.open_zarr(store_path), aoi)

    @classmethod
    def open(cls, store: Path | str, aoi: AreaOfInterest) -> CoherenceStack:
        """Open an existing stack without recomputing."""
        return cls(xr.open_zarr(store), aoi)


def _clip_to_aoi(da: xr.DataArray, aoi: AreaOfInterest) -> xr.DataArray:
    """Clip a 2-D coherence raster to the AOI geometry.

    Geographic (EPSG:4326) grids clip in lon/lat. Projected grids use
    rioxarray with the AOI reprojected into the raster CRS.
    """
    crs = da.attrs.get("crs", "unknown")
    if crs in ("unknown", None) or _coords_look_geographic(da):
        return _clip_geographic(da, aoi)

    try:
        import rioxarray  # noqa: F401
        from pyproj import Transformer
    except ImportError as e:  # pragma: no cover - declared dependency
        raise RuntimeError("rioxarray and pyproj are required to clip projected GUNW") from e

    epsg = int(str(crs).removeprefix("EPSG:"))
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    geom_proj = shapely_transform(transformer.transform, aoi.shape)

    clipped = (
        da.rio.write_crs(f"EPSG:{epsg}", inplace=False)
        .rio.write_nodata(np.nan, inplace=False)
        .rio.clip([mapping(geom_proj)], crs=f"EPSG:{epsg}", drop=True)
    )
    clipped.attrs = dict(da.attrs)
    return clipped


def _clip_geographic(da: xr.DataArray, aoi: AreaOfInterest) -> xr.DataArray:
    """Clip when x/y are lon/lat (toy stacks and already-reprojected grids)."""
    minx, miny, maxx, maxy = aoi.shape.bounds
    x = da["x"]
    y = da["y"]
    x_asc = bool(x.values[-1] >= x.values[0])
    y_asc = bool(y.values[-1] >= y.values[0])
    return da.sel(
        x=slice(minx, maxx) if x_asc else slice(maxx, minx),
        y=slice(miny, maxy) if y_asc else slice(maxy, miny),
    )


def _coords_look_geographic(da: xr.DataArray) -> bool:
    """Heuristic: values in typical lon/lat ranges mean the grid is geographic."""
    x = da["x"].values
    y = da["y"].values
    return bool(np.nanmax(np.abs(x)) <= 180 and np.nanmax(np.abs(y)) <= 90)


def _match_grid(layer: xr.DataArray, reference: xr.DataArray) -> xr.DataArray:
    """Reproject-match ``layer`` onto ``reference``'s (y, x) grid."""
    if layer["x"].identical(reference["x"]) and layer["y"].identical(reference["y"]):
        return layer

    ref_crs = reference.attrs.get("crs", "unknown")
    layer_crs = layer.attrs.get("crs", "unknown")
    same_crs = ref_crs == layer_crs and ref_crs not in ("unknown", None)

    if same_crs and not _coords_look_geographic(reference):
        try:
            import rioxarray  # noqa: F401

            matched = (
                layer.rio.write_crs(ref_crs, inplace=False)
                .rio.write_nodata(np.nan, inplace=False)
                .rio.reproject_match(reference.rio.write_crs(ref_crs, inplace=False))
            )
            # Preserve the time coordinate from the layer being aligned.
            matched = matched.assign_coords(time=layer["time"])
            matched.attrs = dict(layer.attrs)
            return matched
        except Exception as e:
            logger.warning("reproject_match failed (%s); falling back to interp", e)

    # Geographic or fallback: bilinear interp onto the reference grid.
    interp = layer.interp(x=reference["x"], y=reference["y"], method="linear")
    interp.attrs = dict(layer.attrs)
    return interp
