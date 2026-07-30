"""Tests for forest/terrain masks and ERA5 weather joins (offline fixtures)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from understory_core.aoi import AreaOfInterest
from understory_core.masks import (
    combine_masks,
    forest_mask,
    slope_degrees,
    terrain_mask,
    weather_series,
)


@pytest.fixture
def aoi() -> AreaOfInterest:
    return AreaOfInterest(
        name="mask-test",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-55.02, -7.02],
                    [-54.98, -7.02],
                    [-54.98, -6.98],
                    [-55.02, -6.98],
                    [-55.02, -7.02],
                ]
            ],
        },
    )


@pytest.fixture
def grid() -> xr.DataArray:
    n = 10
    return xr.DataArray(
        np.ones((n, n), dtype=np.float32),
        dims=("y", "x"),
        coords={
            "y": np.linspace(-6.985, -7.015, n),
            "x": np.linspace(-55.015, -54.985, n),
        },
        name="coherence",
    )


def test_forest_mask_from_in_memory_landcover(aoi, grid):
    # Left half forest (class 10), right half grassland (class 30).
    xx = np.linspace(-55.03, -54.97, 20)
    yy = np.linspace(-6.97, -7.03, 20)
    values = np.broadcast_to(
        np.where(xx[None, :] < -55.0, 10, 30).astype(np.uint8), (20, 20)
    ).copy()
    lc = xr.DataArray(values, dims=("y", "x"), coords={"y": yy, "x": xx}, name="landcover")

    mask = forest_mask(aoi, grid, landcover=lc)
    assert mask.dims == ("y", "x")
    assert mask.dtype == bool
    # Western columns of the grid should be forest-dominant.
    assert int(mask.isel(x=0).sum()) > int(mask.isel(x=-1).sum())


def test_terrain_mask_masks_steep_slopes(aoi, grid):
    xx = np.linspace(-55.03, -54.97, 30)
    yy = np.linspace(-6.97, -7.03, 30)
    # Flat west, ramp east → steep eastern slope.
    elev = np.tile(np.linspace(0, 800, 30), (30, 1)).astype(np.float32)
    dem = xr.DataArray(elev, dims=("y", "x"), coords={"y": yy, "x": xx}, name="elevation")

    mask = terrain_mask(aoi, grid, dem=dem, max_slope_deg=15.0)
    assert mask.dims == ("y", "x")
    # Western (flat) pixels should survive more often than eastern (steep).
    assert int(mask.isel(x=0).sum()) >= int(mask.isel(x=-1).sum())


def test_slope_degrees_flat_is_near_zero():
    dem = xr.DataArray(
        np.full((5, 5), 100.0, dtype=np.float32),
        dims=("y", "x"),
        coords={"y": np.linspace(-7.0, -7.01, 5), "x": np.linspace(-55.0, -54.99, 5)},
    )
    slope = slope_degrees(dem)
    assert float(slope.max()) < 0.1


def test_weather_series_from_dataframe(aoi):
    times = xr.DataArray(pd.date_range("2026-01-07", periods=3, freq="12D"))
    era5 = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-07", periods=3, freq="12D"),
            "precip_mm": [0.0, 25.0, 5.0],
            "wind_ms": [2.0, 8.0, 3.0],
        }
    )
    weather = weather_series(aoi, times, era5=era5)
    assert list(weather.data_vars) == ["precip_mm", "wind_ms"]
    assert weather.sizes["time"] == 3
    assert float(weather["precip_mm"][1]) == 25.0


def test_weather_series_from_csv(aoi, tmp_path):
    path = tmp_path / "era5.csv"
    path.write_text("time,precip_mm,wind_ms\n2026-01-07,1.5,4.0\n2026-01-19,0.0,2.0\n")
    times = xr.DataArray(pd.to_datetime(["2026-01-07", "2026-01-19"]))
    weather = weather_series(aoi, times, era5=path)
    assert float(weather["precip_mm"][0]) == 1.5


def test_combine_masks(grid):
    a = grid.astype(bool)
    a.values[:] = True
    a.values[:, 5:] = False
    b = grid.astype(bool)
    b.values[:] = True
    b.values[5:, :] = False
    combined = combine_masks(a, b)
    assert int(combined.sum()) == 25  # 5x5 corner
