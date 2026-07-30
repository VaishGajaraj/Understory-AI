"""Ingest tests against a fabricated GUNW-structure HDF5 fixture.

The fixture mirrors the NISAR L2 GUNW product tree closely enough to exercise
explicit selection between the 20 m wrapped-interferogram coherence grid and
the 80 m unwrapped-interferogram grid.
"""

from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pytest
from understory_core.discovery import GunwPair
from understory_core.ingest import extract_coherence, fetch_granule

GRID_ROOT = "science/LSAR/GUNW/grids/frequencyA"


def make_gunw_fixture(path: Path, n_rows: int = 12, n_cols: int = 10) -> np.ndarray:
    rng = np.random.default_rng(5)
    coherence = rng.uniform(0.2, 0.95, size=(n_rows, n_cols)).astype(np.float32)
    with h5py.File(path, "w") as h5:
        wrapped = h5.require_group(f"{GRID_ROOT}/wrappedInterferogram")
        wrapped.create_dataset("HH/coherenceMagnitude", data=coherence)
        wrapped.create_dataset("xCoordinates", data=np.linspace(500_000, 500_180, n_cols))
        wrapped.create_dataset("yCoordinates", data=np.linspace(9_230_000, 9_229_780, n_rows))
        wrapped_projection = wrapped.create_dataset("projection", data=32721)
        wrapped_projection.attrs["epsg_code"] = 32721

        unwrapped = h5.require_group(f"{GRID_ROOT}/unwrappedInterferogram")
        unwrapped.create_dataset("HH/coherenceMagnitude", data=coherence[:6, :5])
        unwrapped.create_dataset("xCoordinates", data=np.linspace(500_000, 500_320, 5))
        unwrapped.create_dataset("yCoordinates", data=np.linspace(9_230_000, 9_229_600, 6))
        unwrapped_projection = unwrapped.create_dataset("projection", data=32721)
        unwrapped_projection.attrs["epsg_code"] = 32721
    return coherence


def test_extract_coherence_from_local_file(tmp_path):
    path = tmp_path / "granule.h5"
    truth = make_gunw_fixture(path)
    da = extract_coherence(path)
    assert da.dims == ("y", "x")
    assert da.shape == truth.shape
    assert np.allclose(da.values, truth)
    assert da.attrs["crs"] == "EPSG:32721"
    assert da.attrs["resolution_m"] == 20
    assert "wrappedInterferogram" in da.attrs["source_path"]
    assert float(da.x[0]) == 500_000
    assert float(da.y[0]) == 9_230_000  # north-up: y descending


def test_extract_selects_80m_layer_explicitly(tmp_path):
    path = tmp_path / "granule.h5"
    truth_20m = make_gunw_fixture(path)
    da = extract_coherence(path, resolution_m=80)
    assert da.shape == (6, 5)
    assert np.allclose(da.values, truth_20m[:6, :5])
    assert da.attrs["resolution_m"] == 80
    assert "unwrappedInterferogram" in da.attrs["source_path"]


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
