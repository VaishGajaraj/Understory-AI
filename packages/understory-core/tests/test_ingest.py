"""Ingest tests against a fabricated GUNW-structure HDF5 fixture.

The fixture mirrors the NISAR L2 GUNW product tree closely enough to exercise
the walker: coherenceMagnitude under an unwrapped-interferogram group, with
xCoordinates/yCoordinates and a projection dataset carrying the EPSG code.
"""

from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pytest
from understory_core.discovery import GunwPair
from understory_core.ingest import extract_coherence, fetch_granule

GRID_GROUP = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"


def make_gunw_fixture(path: Path, n_rows: int = 12, n_cols: int = 10) -> np.ndarray:
    rng = np.random.default_rng(5)
    coherence = rng.uniform(0.2, 0.95, size=(n_rows, n_cols)).astype(np.float32)
    with h5py.File(path, "w") as h5:
        group = h5.require_group(GRID_GROUP)
        group.create_dataset(f"HH/{'coherenceMagnitude'}", data=coherence)
        group.create_dataset("xCoordinates", data=np.linspace(500_000, 500_900, n_cols))
        group.create_dataset("yCoordinates", data=np.linspace(9_230_000, 9_229_000, n_rows))
        projection = group.create_dataset("projection", data=32721)
        projection.attrs["epsg_code"] = 32721
        # A decoy coherence dataset elsewhere (wrapped interferogram) with the
        # same name but different shape — the walker must prefer 'unwrapped'.
        decoy = h5.require_group("science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/HH")
        decoy.create_dataset("coherenceMagnitude", data=coherence[:6, :5])
    return coherence


def test_extract_coherence_from_local_file(tmp_path):
    path = tmp_path / "granule.h5"
    truth = make_gunw_fixture(path)
    da = extract_coherence(path)
    assert da.dims == ("y", "x")
    assert da.shape == truth.shape
    assert np.allclose(da.values, truth)
    assert da.attrs["crs"] == "EPSG:32721"
    assert float(da.x[0]) == 500_000
    assert float(da.y[0]) == 9_230_000  # north-up: y descending


def test_missing_coherence_is_a_clear_error(tmp_path):
    path = tmp_path / "not-gunw.h5"
    with h5py.File(path, "w") as h5:
        h5.create_dataset("unrelated", data=np.zeros(3))
    with pytest.raises(KeyError, match="coherenceMagnitude"):
        extract_coherence(path)


def test_fetch_uses_cache_without_network(tmp_path):
    pair = GunwPair(
        granule_id="cached-granule",
        track=99,
        frame=76,
        flight_direction="DESCENDING",
        reference_start=datetime(2025, 11, 5),
        secondary_start=datetime(2025, 11, 17),
        url="https://example.invalid/never-contacted.h5",
        s3_url=None,
        calibration_tier="beta",
    )
    cached = tmp_path / "cached-granule.h5"
    make_gunw_fixture(cached)
    # url is unreachable by construction — this only passes via the cache
    result = fetch_granule(pair, tmp_path)
    assert result == cached
    da = extract_coherence(pair, cache_dir=tmp_path)
    assert da.attrs["granule_id"] == "cached-granule"
    assert da.attrs["calibration_tier"] == "beta"
