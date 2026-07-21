"""Guards on CoherenceStack.build inputs."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr
from understory_core import stack as stack_module
from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.stack import CoherenceStack, GridSpec, _align_to, _grids_match

AOI = AreaOfInterest(
    name="t",
    geometry={
        "type": "Polygon",
        "coordinates": [
            [[-55.0, -7.0], [-54.9, -7.0], [-54.9, -6.9], [-55.0, -6.9], [-55.0, -7.0]]
        ],
    },
)


def pair(frame: int = 10, tier: str = "beta") -> GunwPair:
    return GunwPair(
        granule_id=f"G-{frame}-{tier}",
        track=99,
        frame=frame,
        flight_direction="DESCENDING",
        reference_start=datetime(2026, 1, 7),
        secondary_start=datetime(2026, 1, 19),
        url="https://example.invalid/g.h5",
        s3_url=None,
        calibration_tier=tier,
    )


def test_zero_pairs_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="zero pairs"):
        CoherenceStack.build(AOI, [], tmp_path / "s.zarr")


def test_mixed_frame_groups_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="frame groups"):
        CoherenceStack.build(AOI, [pair(frame=10), pair(frame=11)], tmp_path / "s.zarr")


def test_mixed_calibration_tiers_are_rejected(tmp_path):
    """Processor differences between tiers make a mixed stack invalid, not merely caveated."""
    pairs = [pair(tier="beta"), pair(tier="provisional")]
    with pytest.raises(ValueError, match="calibration tiers"):
        CoherenceStack.build(AOI, pairs, tmp_path / "s.zarr")


# --- regressions found by pre-push review, each reproduced before fixing -----


def raster(y, x, fill: float = 1.0) -> xr.DataArray:
    return xr.DataArray(
        np.full((len(y), len(x)), fill, np.float32),
        dims=("y", "x"),
        coords={"y": np.asarray(y, float), "x": np.asarray(x, float)},
        name="coherence",
        attrs={"crs": "EPSG:32721"},
    )


# A grid inside AOI's bounds, north-up like a real geocoded product.
AOI_Y = np.linspace(-6.905, -6.995, 5)
AOI_X = np.linspace(-54.995, -54.905, 5)


def build_with(pairs, tmp_path, rasters=None):
    """Run build against synthetic rasters instead of real granules."""
    supplied = iter(rasters) if rasters is not None else None

    def fake_extract(source, cache_dir=None):
        if supplied is not None:
            return next(supplied)
        return raster(AOI_Y, AOI_X)

    with patch.object(stack_module, "extract_coherence", fake_extract):
        return CoherenceStack.build(AOI, pairs, tmp_path / "s.zarr")


def dated_pair(ref_day: int, sec_day: int) -> GunwPair:
    base = datetime(2026, 1, 1)
    return GunwPair(
        granule_id=f"G{ref_day}-{sec_day}",
        track=1,
        frame=2,
        flight_direction="DESCENDING",
        reference_start=base + timedelta(days=ref_day),
        secondary_start=base + timedelta(days=sec_day),
        url="u",
        s3_url=None,
        calibration_tier="beta",
    )


def test_attrs_survive_appending_more_than_one_pair(tmp_path):
    """Appending replaces group attrs, so they must be re-stamped every write.

    calibration_tier living only in a one-pair stack would silently drop the
    field the re-validation gate depends on.
    """
    pairs = [dated_pair(0, 12), dated_pair(12, 24), dated_pair(24, 36)]
    stack = build_with(pairs, tmp_path)
    assert stack.dataset.attrs["calibration_tier"] == "beta"
    assert stack.dataset.attrs["crs"] == "EPSG:32721"
    assert stack.dataset.attrs["track"] == 1


def test_time_axis_is_monotonic_under_mixed_temporal_baselines(tmp_path):
    """Ordering must follow the midpoint written, not reference_start.

    The rolling baseline shifts positionally, so a scrambled time index means
    the trailing window is not trailing in time -- and nothing would raise.
    """
    pairs = [dated_pair(0, 48), dated_pair(12, 24), dated_pair(24, 36)]
    times = build_with(pairs, tmp_path).dataset.time.values
    assert np.all(np.diff(times) > np.timedelta64(0, "ns")), [str(t)[:10] for t in times]


def test_duplicate_midpoints_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="share midpoint"):
        build_with([dated_pair(0, 12), dated_pair(0, 12)], tmp_path)


def test_edge_granule_on_the_same_lattice_is_reindexed_not_rejected():
    """Two granules on one lattice with different extents differ by whole
    pixels; checking absolute origin offset rejected exactly the case the
    reindex path exists for."""
    grid = GridSpec.of(raster(np.arange(10), np.arange(10)))
    shifted = raster(np.arange(1, 11), np.arange(1, 11))
    aligned = _align_to(shifted, grid, "G1")
    assert aligned.shape == (10, 10)
    assert np.isnan(aligned.values).any()  # non-overlapping edge is NaN-filled


def test_off_lattice_granule_is_rejected():
    grid = GridSpec.of(raster(np.arange(10), np.arange(10)))
    half_pixel = raster(np.arange(10) + 0.5, np.arange(10) + 0.5)
    with pytest.raises(ValueError, match="off the stack grid"):
        _align_to(half_pixel, grid, "G2")


def test_anisotropic_grid_uses_per_dimension_spacing():
    """A y misregistration must be judged against y spacing, not x spacing.

    With one shared tolerance a 0.9-pixel y shift passed the check and was then
    snapped by nearest-neighbour, duplicating a row with no warning.
    """
    grid = GridSpec.of(raster(np.arange(20), np.arange(0, 2000, 100)))
    misregistered = raster(np.arange(20) + 0.9, np.arange(0, 2000, 100))
    with pytest.raises(ValueError, match="off the stack grid in y"):
        _align_to(misregistered, grid, "G3")


def test_single_column_grid_does_not_crash():
    """A one-pixel-wide clip has no measurable spacing; that is not an error."""
    grid = GridSpec.of(raster(np.arange(5), [0.0]))
    assert _align_to(raster(np.arange(4), [0.0]), grid, "G4").shape == (5, 1)
    assert GridSpec.of(raster(np.arange(5), [0.0])).spacing("x") == 0.0


def test_identical_grid_takes_the_fast_path():
    grid = GridSpec.of(raster(np.arange(10), np.arange(10)))
    assert _grids_match(raster(np.arange(10), np.arange(10)), grid)
    assert not _grids_match(raster(np.arange(9), np.arange(10)), grid)
