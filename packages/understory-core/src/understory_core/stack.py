"""Coherence time-series stack construction.

A CoherenceStack is the central data structure of the whole project: a
per-pixel time series of 12-day coherence values over an AOI, stored as a
Zarr-backed xarray Dataset with dims (time, y, x). Everything downstream —
baselines, detectors, scoring — consumes this.
"""

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

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.ingest import extract_coherence

logger = logging.getLogger(__name__)

# Pairs in one frame group are produced on the NISAR SDS's fixed frame grid, so
# their coordinate vectors should match to well under a pixel. Anything beyond
# this is a geometry error worth failing on, not resampling away.
GRID_TOLERANCE_FRACTION = 0.01

# Spatial chunking for the written Zarr, matching the tiling unit downstream.
# Time is chunked at 1 because pairs are appended one at a time; a per-pixel
# time-series read therefore touches one chunk per timestep. Rechunking time
# after the build would suit the detector's access pattern better, and is worth
# doing once real stacks are large enough for it to matter.
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

    @classmethod
    def build(
        cls,
        aoi: AreaOfInterest,
        pairs: list[GunwPair],
        store: Path | str,
        *,
        cache_dir: Path | None = None,
        spatial_chunk: int = DEFAULT_SPATIAL_CHUNK,
    ) -> CoherenceStack:
        """Extract coherence for each pair, clip to the AOI, align on a common
        grid, and stack along time (indexed by pair midpoint date).

        ``pairs`` must come from a single frame group (see
        ``discovery.group_by_frame``) — mixing geometries corrupts the
        per-pixel time series.

        Pairs are appended to the Zarr store one at a time rather than
        concatenated in memory: a year of 20 m coherence over one frame is
        ~19 GB, which does not fit anywhere convenient. Peak memory here is one
        granule's clipped raster plus the grid's coordinate vectors.

        **Resume semantics.** The build is idempotent and resumable. Pairs
        define the full intended time series, ordered by midpoint, and are
        appended in that order — so an interrupted build always leaves a store
        holding a *prefix* of that series. A companion ``<store>.build.json``
        marker records how many timesteps were durably committed (written only
        after each ``to_zarr`` returns), which is what makes "survived a kill"
        answerable: on resume the store's own time axis must have exactly that
        many steps and they must equal the leading pairs of this list, or the
        build refuses rather than guessing. It then appends only the missing
        tail. Re-running with the same list is a no-op; a store built from a
        different pair set, tier, or frame — or one whose length disagrees with
        its marker (an interrupted, possibly torn append) — is refused with an
        actionable error rather than silently duplicated or trusted.
        """
        if not pairs:
            raise ValueError("cannot build a stack from zero pairs")
        frame_keys = {p.frame_key for p in pairs}
        if len(frame_keys) > 1:
            raise ValueError(
                f"pairs span {len(frame_keys)} frame groups {sorted(frame_keys)} — build one "
                "stack per frame group (understory_core.discovery.group_by_frame); mixing "
                "geometries corrupts the per-pixel time series"
            )
        tiers = {p.calibration_tier for p in pairs}
        if len(tiers) > 1:
            raise ValueError(
                f"pairs span calibration tiers {sorted(tiers)} — ASF states that processor "
                "differences between tiers produce artifacts, so a stack mixing them is not "
                "a valid time series. Build one stack per tier and compare them; do not "
                "concatenate. See docs/ARCHIVE_STATUS.md."
            )

        # Sort by the coordinate actually written. Sorting by reference_start
        # instead lets a frame group with mixed temporal baselines produce a
        # non-monotonic time axis, which the detector would not notice: the
        # rolling baseline shifts and windows *positionally*, so a scrambled
        # index silently means the "trailing window" is not trailing in time.
        ordered = sorted(pairs, key=lambda p: p.midpoint)
        # p.midpoint is always a real datetime, so pd.Timestamp never returns
        # NaT here; the cast tells the type checker what the stub's union hides.
        midpoints = cast("list[pd.Timestamp]", [pd.Timestamp(p.midpoint) for p in ordered])
        duplicates = {t for t in midpoints if midpoints.count(t) > 1}
        if duplicates:
            raise ValueError(
                f"pairs share midpoint(s) {sorted(str(t) for t in duplicates)} — a coherence "
                "time series cannot have two observations at one timestep. Deduplicate the "
                "pair list (understory_core.discovery.single_cycle_pairs keeps one baseline)."
            )

        store = Path(store)
        frame_key = next(iter(frame_keys))
        tier = next(iter(tiers))
        committed = _resume_point(store, midpoints, frame_key, tier)
        if committed == len(ordered):
            logger.info("stack already complete at %s (%d timesteps)", store, committed)
            return cls.open(store, aoi)

        grid: GridSpec | None = None
        attrs: dict = {}
        if committed > 0:
            # Resuming: pin the grid and attrs to what the store already holds
            # so appended rasters land on exactly its lattice, not merely a
            # compatible one derived from the next granule.
            grid, attrs = _grid_and_attrs_of(store)

        for index in range(committed, len(ordered)):
            pair, midpoint = ordered[index], midpoints[index]
            raster = _clip_to_aoi(extract_coherence(pair, cache_dir=cache_dir), aoi)
            if grid is None:
                # Coordinate vectors only. Alignment needs nothing else, and
                # holding the first granule's full raster for the whole build
                # would keep two full arrays live at once.
                grid = GridSpec.of(raster)
                attrs = {
                    "aoi": aoi.name,
                    "track": pair.track,
                    "frame": pair.frame,
                    "flight_direction": pair.flight_direction,
                    "calibration_tier": pair.calibration_tier,
                    "crs": raster.attrs.get("crs", "unknown"),
                }
            else:
                raster = _align_to(raster, grid, pair.granule_id)

            step = raster.expand_dims(time=[midpoint]).to_dataset(name="coherence")
            step = step.chunk({"time": 1, "y": spatial_chunk, "x": spatial_chunk})
            # Re-stamped on every write: appending with mode="a" replaces the
            # group's attributes with the incoming dataset's, so setting them
            # only on the first pair leaves a multi-pair stack with none — and
            # calibration_tier is the field the re-validation gate depends on.
            step.attrs = attrs
            if index == 0:
                step.to_zarr(store, mode="w")
            else:
                step.to_zarr(store, mode="a", append_dim="time")
            # Record the commit only after the write returns, so the marker
            # never claims a timestep the store does not durably hold.
            _write_marker(store, midpoints[: index + 1], frame_key, tier)
            logger.info("stacked %d/%d %s", index + 1, len(ordered), pair.granule_id)

        return cls.open(store, aoi)

    @classmethod
    def open(cls, store: Path | str, aoi: AreaOfInterest) -> CoherenceStack:
        """Open an existing stack without recomputing."""
        return cls(xr.open_zarr(store), aoi)


def _marker_path(store: Path) -> Path:
    """The build marker beside the store (not inside it, to keep Zarr clean)."""
    return Path(str(store) + ".build.json")


def _write_marker(
    store: Path, midpoints: Sequence[pd.Timestamp], frame_key: tuple[int, int, str], tier: str
) -> None:
    """Record the committed timesteps, atomically.

    Written via a temp file and a rename so a kill mid-write cannot leave a
    half-parsed marker — the marker's own integrity is the thing resume leans
    on, so it must not be the weak link.
    """
    marker = {
        "committed": len(midpoints),
        "midpoints": [pd.Timestamp(m).isoformat() for m in midpoints],
        "frame_key": list(frame_key),
        "calibration_tier": tier,
    }
    path = _marker_path(store)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(marker))
    tmp.replace(path)


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
) -> int:
    """How many leading timesteps the store already holds, or refuse.

    Returns 0 for a fresh build (no store), or the committed count when the
    store is a verified prefix of ``midpoints`` for this frame and tier. Any
    inconsistency — a store with no marker, a length that disagrees with the
    marker, a divergent time axis, or a different frame/tier — raises rather
    than risking a duplicated or scrambled time series.
    """
    if not store.exists():
        # A stale marker with no store (store deleted out from under it) is
        # simply ignored; the fresh build below overwrites it.
        return 0

    marker = _read_marker(store)
    if marker is None:
        raise ValueError(
            f"stack store {store} exists but has no build marker "
            f"({_marker_path(store).name}); which of its timesteps are complete cannot "
            "be verified. Delete the store and rebuild."
        )

    committed = int(marker.get("committed", 0))
    try:
        # consolidated=False: an append updates each array's own metadata and
        # only then the consolidated snapshot, so after a kill the snapshot can
        # describe a store that no longer exists. Resume must judge the arrays
        # themselves — the snapshot is a read optimisation, not the truth.
        with xr.open_zarr(store, consolidated=False) as existing:
            store_times = pd.DatetimeIndex(pd.to_datetime(existing.time.values))
            coherence_steps = int(existing["coherence"].sizes["time"])
    except ValueError as exc:
        # A Zarr append extends the time coordinate and the coherence variable
        # as two separate arrays; a kill between the two shape writes leaves
        # them disagreeing, and open_zarr then fails with "conflicting sizes"
        # before any of the checks below can run. That torn state is exactly
        # what resume exists to catch, so it gets the actionable message, not
        # an internal xarray error.
        if "conflicting sizes" in str(exc):
            raise ValueError(
                f"stack store {store} is torn: its time coordinate and coherence variable "
                "disagree on length — a kill landed between the two shape writes of an "
                "append. Which timesteps are complete cannot be determined. Delete the "
                "store and rebuild."
            ) from exc
        raise
    if coherence_steps != len(store_times):
        raise ValueError(
            f"stack store {store} is torn: coherence holds {coherence_steps} timesteps but "
            f"the time coordinate holds {len(store_times)} — an interrupted append. Delete "
            "the store and rebuild."
        )
    if len(store_times) != committed:
        raise ValueError(
            f"stack store {store} holds {len(store_times)} timesteps but its build marker "
            f"records {committed} committed — an interrupted append left it indeterminate. "
            "Delete the store and rebuild."
        )
    if committed > len(midpoints):
        raise ValueError(
            f"stack store {store} holds {committed} timesteps, more than the {len(midpoints)} "
            "pairs supplied — this pair list is not the one it was built from. Delete the "
            "store and rebuild."
        )
    if marker.get("calibration_tier") != tier:
        raise ValueError(
            f"stack store {store} was built at tier '{marker.get('calibration_tier')}', not "
            f"'{tier}' — tiers must not be mixed in one stack. Build a separate store per tier."
        )
    recorded_frame = marker.get("frame_key")
    # A corrupted marker can hold anything JSON allows here; a scalar would make
    # tuple() raise TypeError instead of the actionable refusal every other
    # malformed-marker state gets.
    frame_tuple = tuple(recorded_frame) if isinstance(recorded_frame, list | tuple) else None
    if frame_tuple != frame_key:
        raise ValueError(
            f"stack store {store} was built for frame {frame_tuple or recorded_frame!r}, "
            f"not {frame_key} — one stack per frame group. Build a separate store per frame."
        )
    expected = pd.DatetimeIndex([pd.Timestamp(m) for m in midpoints[:committed]])
    if not store_times.equals(expected):
        raise ValueError(
            f"stack store {store}'s timesteps do not match the leading pairs of this list — it "
            "was built from a different pair set. Delete the store and rebuild."
        )
    return committed


def _grid_and_attrs_of(store: Path) -> tuple[GridSpec, dict]:
    """The grid and attrs an existing store is pinned to, for resume.

    A resumed append must land on the store's own lattice and re-stamp its own
    attrs, not a compatible grid inferred from the next granule.
    """
    with xr.open_zarr(store, consolidated=False) as existing:
        grid = GridSpec(y=np.asarray(existing["y"].values), x=np.asarray(existing["x"].values))
        attrs = dict(existing.attrs)
    return grid, attrs


def _clip_to_aoi(raster: xr.DataArray, aoi: AreaOfInterest) -> xr.DataArray:
    """Clip a granule raster to the AOI's bounding box.

    Bounding box, not exact geometry: the detector's own filters handle shape,
    and a rasterized polygon mask here would cost a full-size boolean array per
    granule for no gain.
    """
    min_x, min_y, max_x, max_y = aoi.shape.bounds
    # Coordinate vectors may run in either direction; slice accordingly.
    y_slice = slice(max_y, min_y) if raster["y"][0] > raster["y"][-1] else slice(min_y, max_y)
    clipped = raster.sel(x=slice(min_x, max_x), y=y_slice)
    if clipped.sizes["x"] == 0 or clipped.sizes["y"] == 0:
        raise ValueError(
            f"granule {raster.attrs.get('granule_id', '?')} does not overlap AOI "
            f"'{aoi.name}' bounds {aoi.shape.bounds} — check the AOI is inside the frame "
            "footprint, and that both are in the same CRS "
            f"(granule crs: {raster.attrs.get('crs', 'unknown')})"
        )
    return clipped


@dataclass(frozen=True)
class GridSpec:
    """The y/x coordinate vectors a frame group's stack is pinned to.

    Just the two 1-D vectors, not the raster: alignment needs nothing else, and
    keeping a whole granule alive as the reference doubles a build's peak memory
    for no benefit.
    """

    y: np.ndarray
    x: np.ndarray

    @classmethod
    def of(cls, raster: xr.DataArray) -> GridSpec:
        return cls(y=np.asarray(raster["y"].values), x=np.asarray(raster["x"].values))

    def vector(self, dim: str) -> np.ndarray:
        return self.y if dim == "y" else self.x

    def spacing(self, dim: str) -> float:
        """Pixel spacing along ``dim``, or 0.0 when the axis has one element.

        Zero is a real answer for a single-column clip, and callers must handle
        it — deriving spacing from the other axis instead would apply an x
        tolerance to a y offset, which is exactly the bug this replaces.
        """
        vector = self.vector(dim)
        if vector.size < 2:
            return 0.0
        return abs(float(vector[1] - vector[0]))


def _align_to(raster: xr.DataArray, grid: GridSpec, granule_id: str) -> xr.DataArray:
    """Put a granule raster on the stack's grid, or fail loudly.

    Within a frame group every product comes off the same fixed NISAR frame
    grid, so this is a check plus a reindex, never a resample. A real geometry
    mismatch means the pairs were grouped wrongly, and silently interpolating it
    away would corrupt the time series it is meant to protect.

    What is checked is grid *phase* — the offset modulo the pixel spacing — not
    the absolute origin difference. Two granules on one lattice covering
    different extents differ in origin by whole pixels, which is precisely the
    edge-granule case that has to be reindexed rather than rejected.
    """
    if _grids_match(raster, grid):
        return raster.assign_coords(y=grid.y, x=grid.x)

    for dim in ("y", "x"):
        spacing = grid.spacing(dim)
        if spacing == 0.0 or raster.sizes[dim] == 0:
            continue
        offset = abs(float(raster[dim].values[0] - grid.vector(dim)[0]))
        phase = offset % spacing
        # Fold [spacing-eps, spacing) back to a near-zero misregistration.
        phase = min(phase, spacing - phase)
        if phase > spacing * GRID_TOLERANCE_FRACTION:
            raise ValueError(
                f"granule {granule_id} is off the stack grid in {dim}: its samples fall "
                f"{phase:.6g} from the lattice, against a pixel spacing of {spacing:.6g}. "
                "Pairs in one frame group share a grid; this usually means discovery grouped "
                "pairs from different frames, or the product tree changed."
            )

    # Same lattice, different extent (edge granule) — line up on the reference.
    # Reindexed one dimension at a time so each gets its own tolerance; a single
    # reindex_like would apply one dimension's half-pixel to both, and on an
    # anisotropic grid that silently snaps a row instead of NaN-filling it.
    aligned = raster
    for dim, vector in (("y", grid.y), ("x", grid.x)):
        spacing = grid.spacing(dim)
        tolerance = spacing / 2 if spacing else None
        aligned = aligned.reindex({dim: vector}, method="nearest", tolerance=tolerance)
    return aligned


def _grids_match(raster: xr.DataArray, grid: GridSpec) -> bool:
    for dim in ("y", "x"):
        vector = grid.vector(dim)
        if raster.sizes[dim] != vector.size:
            return False
        spacing = grid.spacing(dim)
        atol = spacing * GRID_TOLERANCE_FRACTION
        if not np.allclose(raster[dim].values, vector, rtol=0, atol=atol):
            return False
    return True
