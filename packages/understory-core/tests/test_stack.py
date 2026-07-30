"""Tests for CoherenceStack.build against fabricated GUNW HDF5 fixtures."""

from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pytest
from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.stack import CoherenceStack

GRID_GROUP = "science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram"


def make_geographic_gunw(
    path: Path,
    *,
    coherence: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
) -> None:
    """Write a GUNW-shaped HDF5 whose x/y are lon/lat (EPSG:4326)."""
    with h5py.File(path, "w") as h5:
        group = h5.require_group(GRID_GROUP)
        group.create_dataset("HH/coherenceMagnitude", data=coherence.astype(np.float32))
        group.create_dataset("xCoordinates", data=lons)
        group.create_dataset("yCoordinates", data=lats)
        projection = group.create_dataset("projection", data=4326)
        projection.attrs["epsg_code"] = 4326


def make_pair(granule_id: str, ref: str, sec: str) -> GunwPair:
    return GunwPair(
        granule_id=granule_id,
        track=10,
        frame=20,
        flight_direction="DESCENDING",
        reference_start=datetime.fromisoformat(ref),
        secondary_start=datetime.fromisoformat(sec),
        url=f"https://example.invalid/{granule_id}.h5",
        s3_url=None,
        calibration_tier="beta",
    )


@pytest.fixture
def aoi() -> AreaOfInterest:
    return AreaOfInterest(
        name="stack-test",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-55.02, -7.01],
                    [-54.98, -7.01],
                    [-54.98, -6.99],
                    [-55.02, -6.99],
                    [-55.02, -7.01],
                ]
            ],
        },
    )


def test_build_stacks_pairs_by_midpoint(tmp_path, aoi):
    n_rows, n_cols = 20, 20
    lons = np.linspace(-55.03, -54.97, n_cols)
    lats = np.linspace(-6.98, -7.02, n_rows)  # north-up
    cache = tmp_path / "granules"
    cache.mkdir()

    pairs = []
    for i, (ref, sec) in enumerate(
        [
            ("2026-01-01T00:00:00", "2026-01-13T00:00:00"),
            ("2026-01-13T00:00:00", "2026-01-25T00:00:00"),
            ("2026-01-25T00:00:00", "2026-02-06T00:00:00"),
        ]
    ):
        gid = f"pair-{i}"
        make_geographic_gunw(
            cache / f"{gid}.h5",
            coherence=np.full((n_rows, n_cols), 0.5 + 0.1 * i, dtype=np.float32),
            lons=lons,
            lats=lats,
        )
        pairs.append(make_pair(gid, ref, sec))

    store = tmp_path / "stack.zarr"
    stack = CoherenceStack.build(aoi, pairs, store, cache_dir=cache)

    assert store.exists()
    assert stack.coherence.dims == ("time", "y", "x")
    assert stack.coherence.sizes["time"] == 3
    # Midpoints: Jan 7, Jan 19, Jan 31
    times = [str(t)[:10] for t in stack.coherence["time"].values]
    assert times == ["2026-01-07", "2026-01-19", "2026-01-31"]
    # Clipped to AOI — smaller than full granule
    assert stack.coherence.sizes["x"] < n_cols
    assert stack.coherence.sizes["y"] < n_rows
    assert stack.dataset.attrs["calibration_tiers"] == "beta"
    assert stack.dataset.attrs["resolution_m"] == 20
    assert stack.dataset.attrs["polarization"] == "HH"
    assert stack.dataset.attrs["granule_ids"] == ["pair-0", "pair-1", "pair-2"]
    # reopen path works
    reopened = CoherenceStack.open(store, aoi)
    assert reopened.coherence.shape == stack.coherence.shape


def test_build_rejects_mixed_frames(tmp_path, aoi):
    p1 = make_pair("a", "2026-01-01T00:00:00", "2026-01-13T00:00:00")
    p2 = GunwPair(
        granule_id="b",
        track=10,
        frame=21,  # different frame
        flight_direction="DESCENDING",
        reference_start=datetime(2026, 1, 13),
        secondary_start=datetime(2026, 1, 25),
        url="https://example.invalid/b.h5",
        s3_url=None,
        calibration_tier="beta",
    )
    with pytest.raises(ValueError, match="frame groups"):
        CoherenceStack.build(aoi, [p1, p2], tmp_path / "x.zarr")


def test_build_rejects_empty_pairs(tmp_path, aoi):
    with pytest.raises(ValueError, match="at least one"):
        CoherenceStack.build(aoi, [], tmp_path / "x.zarr")


def test_with_valid_mask(aoi):
    import pandas as pd
    import xarray as xr

    n = 8
    ds = xr.Dataset(
        {"coherence": (("time", "y", "x"), np.ones((2, n, n), dtype=np.float32))},
        coords={
            "time": pd.date_range("2026-01-01", periods=2, freq="12D"),
            "y": np.linspace(-6.99, -7.01, n),
            "x": np.linspace(-55.01, -54.99, n),
        },
    )
    stack = CoherenceStack(ds, aoi)
    mask = xr.DataArray(
        np.zeros((n, n), dtype=bool),
        dims=("y", "x"),
        coords={"y": ds["y"], "x": ds["x"]},
    )
    mask.values[2:5, 2:5] = True
    masked = stack.with_valid_mask(mask)
    assert masked.valid is not None
    assert int(masked.valid.sum()) == 9
