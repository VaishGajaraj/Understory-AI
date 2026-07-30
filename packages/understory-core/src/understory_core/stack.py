"""Resumable construction of projected NISAR coherence time-series stacks."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.ingest import extract_coherence

logger = logging.getLogger(__name__)

# Pairs in one frame group should share the NISAR SDS fixed grid. A larger
# offset is a geometry error, not an invitation to silently resample the data.
GRID_TOLERANCE_FRACTION = 0.01
DEFAULT_SPATIAL_CHUNK = 512


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
        """Optional (y, x) boolean mask of pixels trusted for detection."""
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
        dataset = self.dataset.copy()
        dataset["valid"] = aligned.fillna(False)
        return CoherenceStack(dataset, self.aoi)

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
        spatial_chunk: int = DEFAULT_SPATIAL_CHUNK,
    ) -> CoherenceStack:
        """Build or resume one scientifically frozen coherence stack.

        Pairs must share frame geometry and calibration tier. Each clipped
        raster is appended independently, bounding peak memory to roughly one
        granule. A sidecar build marker records the committed prefix so a
        repeated command is idempotent and an interrupted append is refused
        rather than trusted.
        """
        if not pairs:
            raise ValueError("CoherenceStack.build requires at least one GUNW pair")
        frame_keys = {pair.frame_key for pair in pairs}
        if len(frame_keys) > 1:
            raise ValueError(
                f"pairs span {len(frame_keys)} frame groups {sorted(frame_keys)}; "
                "build one stack per frame group (see discovery.group_by_frame)"
            )
        tiers = {pair.calibration_tier for pair in pairs}
        if len(tiers) > 1:
            raise ValueError(
                f"pairs span calibration tiers {sorted(tiers)}; processor differences between "
                "tiers can resemble landscape change, so build a separate stack per tier"
            )

        ordered = sorted(pairs, key=lambda pair: pair.midpoint)
        midpoints = cast("list[pd.Timestamp]", [pd.Timestamp(pair.midpoint) for pair in ordered])
        duplicates = {timestamp for timestamp in midpoints if midpoints.count(timestamp) > 1}
        if duplicates:
            raise ValueError(
                f"pairs share midpoint(s) {sorted(str(value) for value in duplicates)}; "
                "deduplicate the pair list before building a time series"
            )

        store_path = Path(store)
        cache = Path(cache_dir) if cache_dir else Path("data/scratch/granules")
        frame_key = next(iter(frame_keys))
        tier = next(iter(tiers))
        layer = {
            "resolution_m": resolution_m,
            "polarization": polarization.upper(),
            "frequency": frequency,
        }
        committed = _resume_point(store_path, midpoints, frame_key, tier, layer)
        if committed == len(ordered):
            logger.info("stack already complete at %s (%d timesteps)", store_path, committed)
            return cls.open(store_path, aoi)

        grid: GridSpec | None = None
        attrs: dict = {}
        if committed > 0:
            grid, attrs = _grid_and_attrs_of(store_path)

        attrs.update(
            {
                "aoi": aoi.name,
                "track": ordered[0].track,
                "frame": ordered[0].frame,
                "flight_direction": ordered[0].flight_direction,
                "calibration_tiers": tier,
                "n_pairs": len(ordered),
                "resolution_m": resolution_m,
                "polarization": polarization.upper(),
                "frequency": frequency,
                "granule_ids": [pair.granule_id for pair in ordered],
            }
        )

        for index in range(committed, len(ordered)):
            pair = ordered[index]
            raster = extract_coherence(
                pair,
                cache_dir=cache,
                resolution_m=resolution_m,
                polarization=polarization,
                frequency=frequency,
            )
            raster = _clip_to_aoi(raster, aoi)
            if grid is None:
                grid = GridSpec.of(raster)
                attrs["crs"] = raster.attrs.get("crs", "unknown")
            else:
                raster = _align_to(raster, grid, pair.granule_id)

            step = raster.expand_dims(time=[midpoints[index]]).to_dataset(name="coherence")
            step = step.chunk({"time": 1, "y": spatial_chunk, "x": spatial_chunk})
            step.attrs = attrs
            if index == 0:
                store_path.parent.mkdir(parents=True, exist_ok=True)
                step.to_zarr(store_path, mode="w")
            else:
                step.to_zarr(store_path, mode="a", append_dim="time")
            _write_marker(
                store_path,
                midpoints[: index + 1],
                frame_key,
                tier,
                layer,
            )
            logger.info("stacked %d/%d %s", index + 1, len(ordered), pair.granule_id)

        return cls.open(store_path, aoi)

    @classmethod
    def open(cls, store: Path | str, aoi: AreaOfInterest) -> CoherenceStack:
        """Open an existing stack without recomputing."""
        return cls(xr.open_zarr(store), aoi)


def _marker_path(store: Path) -> Path:
    return Path(str(store) + ".build.json")


def _write_marker(
    store: Path,
    midpoints: Sequence[pd.Timestamp],
    frame_key: tuple[int, int, str],
    tier: str,
    layer: dict,
) -> None:
    """Record committed timesteps atomically after each successful append."""
    marker = {
        "schema_version": "1",
        "committed": len(midpoints),
        "midpoints": [pd.Timestamp(midpoint).isoformat() for midpoint in midpoints],
        "frame_key": list(frame_key),
        "calibration_tier": tier,
        "layer": layer,
    }
    path = _marker_path(store)
    temporary = path.parent / (path.name + ".tmp")
    temporary.write_text(json.dumps(marker))
    temporary.replace(path)


def _read_marker(store: Path) -> dict | None:
    path = _marker_path(store)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _resume_point(
    store: Path,
    midpoints: Sequence[pd.Timestamp],
    frame_key: tuple[int, int, str],
    tier: str,
    layer: dict,
) -> int:
    """Return the verified committed prefix length, or reject ambiguous state."""
    if not store.exists():
        return 0
    marker = _read_marker(store)
    if marker is None:
        raise ValueError(f"stack store {store} has no build marker; delete it and rebuild")

    committed = int(marker.get("committed", 0))
    try:
        with xr.open_zarr(store, consolidated=False) as existing:
            store_times = pd.DatetimeIndex(pd.to_datetime(existing.time.values))
            coherence_steps = int(existing["coherence"].sizes["time"])
    except ValueError as error:
        if "conflicting sizes" in str(error):
            raise ValueError(
                f"stack store {store} is torn after an interrupted append; delete it and rebuild"
            ) from error
        raise
    if coherence_steps != len(store_times) or len(store_times) != committed:
        raise ValueError(
            f"stack store {store} disagrees with its build marker after an interrupted append; "
            "delete it and rebuild"
        )
    if committed > len(midpoints):
        raise ValueError(
            f"stack store {store} has more timesteps than the supplied pair list; "
            "delete it and rebuild"
        )
    if marker.get("calibration_tier") != tier:
        raise ValueError(
            f"stack store {store} was built at tier "
            f"{marker.get('calibration_tier')!r}, not {tier!r}"
        )
    if marker.get("layer") != layer:
        raise ValueError(
            f"stack store {store} was built from layer {marker.get('layer')!r}, not {layer!r}"
        )
    recorded_frame = marker.get("frame_key")
    frame_tuple = tuple(recorded_frame) if isinstance(recorded_frame, list | tuple) else None
    if frame_tuple != frame_key:
        raise ValueError(
            f"stack store {store} was built for frame {frame_tuple or recorded_frame!r}, "
            f"not {frame_key}"
        )
    expected = pd.DatetimeIndex([pd.Timestamp(value) for value in midpoints[:committed]])
    if not store_times.equals(expected):
        raise ValueError(
            f"stack store {store} does not match the leading pairs of this list; "
            "delete it and rebuild"
        )
    return committed


def _grid_and_attrs_of(store: Path) -> tuple[GridSpec, dict]:
    with xr.open_zarr(store, consolidated=False) as existing:
        grid = GridSpec(y=np.asarray(existing["y"].values), x=np.asarray(existing["x"].values))
        attrs = dict(existing.attrs)
    return grid, attrs


def _clip_to_aoi(raster: xr.DataArray, aoi: AreaOfInterest) -> xr.DataArray:
    """Clip geographic or projected GUNW data without changing its native CRS."""
    crs = raster.attrs.get("crs", "unknown")
    if crs in ("unknown", None) or _coords_look_geographic(raster):
        clipped = _clip_geographic(raster, aoi)
    else:
        try:
            import rioxarray  # noqa: F401
            from pyproj import Transformer
        except ImportError as error:  # pragma: no cover - declared dependencies
            raise RuntimeError("rioxarray and pyproj are required for projected GUNW") from error

        transformer = Transformer.from_crs("EPSG:4326", str(crs), always_xy=True)
        projected = shapely_transform(transformer.transform, aoi.shape)
        clipped = (
            raster.rio.write_crs(str(crs), inplace=False)
            .rio.write_nodata(np.nan, inplace=False)
            .rio.clip([mapping(projected)], crs=str(crs), drop=True)
        )
        clipped.attrs = dict(raster.attrs)
    if clipped.sizes["x"] == 0 or clipped.sizes["y"] == 0:
        raise ValueError(
            f"granule {raster.attrs.get('granule_id', '?')} does not overlap AOI {aoi.name!r}"
        )
    return clipped


def _clip_geographic(raster: xr.DataArray, aoi: AreaOfInterest) -> xr.DataArray:
    min_x, min_y, max_x, max_y = aoi.shape.bounds
    x_ascending = bool(raster["x"].values[-1] >= raster["x"].values[0])
    y_ascending = bool(raster["y"].values[-1] >= raster["y"].values[0])
    return raster.sel(
        x=slice(min_x, max_x) if x_ascending else slice(max_x, min_x),
        y=slice(min_y, max_y) if y_ascending else slice(max_y, min_y),
    )


def _coords_look_geographic(raster: xr.DataArray) -> bool:
    x = raster["x"].values
    y = raster["y"].values
    return bool(np.nanmax(np.abs(x)) <= 180 and np.nanmax(np.abs(y)) <= 90)


@dataclass(frozen=True)
class GridSpec:
    """Coordinate vectors defining one frame group's fixed raster lattice."""

    y: np.ndarray
    x: np.ndarray

    @classmethod
    def of(cls, raster: xr.DataArray) -> GridSpec:
        return cls(y=np.asarray(raster["y"].values), x=np.asarray(raster["x"].values))

    def vector(self, dimension: str) -> np.ndarray:
        return self.y if dimension == "y" else self.x

    def spacing(self, dimension: str) -> float:
        vector = self.vector(dimension)
        if vector.size < 2:
            return 0.0
        return abs(float(vector[1] - vector[0]))


def _align_to(raster: xr.DataArray, grid: GridSpec, granule_id: str) -> xr.DataArray:
    """Align compatible extents on one fixed frame lattice without resampling."""
    if _grids_match(raster, grid):
        return raster.assign_coords(y=grid.y, x=grid.x)

    for dimension in ("y", "x"):
        spacing = grid.spacing(dimension)
        if spacing == 0.0 or raster.sizes[dimension] == 0:
            continue
        offset = abs(float(raster[dimension].values[0] - grid.vector(dimension)[0]))
        phase = offset % spacing
        phase = min(phase, spacing - phase)
        if phase > spacing * GRID_TOLERANCE_FRACTION:
            raise ValueError(
                f"granule {granule_id} is off the stack grid in {dimension}: "
                f"phase {phase:.6g}, pixel spacing {spacing:.6g}"
            )

    aligned = raster
    for dimension, vector in (("y", grid.y), ("x", grid.x)):
        spacing = grid.spacing(dimension)
        tolerance = spacing / 2 if spacing else None
        aligned = aligned.reindex({dimension: vector}, method="nearest", tolerance=tolerance)
    aligned.attrs = dict(raster.attrs)
    return aligned


def _grids_match(raster: xr.DataArray, grid: GridSpec) -> bool:
    for dimension in ("y", "x"):
        vector = grid.vector(dimension)
        if raster.sizes[dimension] != vector.size:
            return False
        tolerance = grid.spacing(dimension) * GRID_TOLERANCE_FRACTION
        if not np.allclose(raster[dimension].values, vector, rtol=0, atol=tolerance):
            return False
    return True
