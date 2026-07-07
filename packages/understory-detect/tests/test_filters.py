import numpy as np
import pandas as pd
import xarray as xr
from understory_detect.filters import cluster_filter, linearity_score, persistence_filter


def mask_from(values: np.ndarray) -> xr.DataArray:
    t, ny, nx = values.shape
    return xr.DataArray(
        values.astype(bool),
        dims=("time", "y", "x"),
        coords={
            "time": pd.date_range("2026-01-01", periods=t, freq="12D"),
            "y": np.arange(ny),
            "x": np.arange(nx),
        },
    )


def test_persistence_kills_transients():
    values = np.zeros((4, 2, 2))
    values[1, 0, 0] = 1  # one-off blip
    values[2:, 1, 1] = 1  # persistent from t2
    result = persistence_filter(mask_from(values), min_pairs=2)
    assert not result.values[:, 0, 0].any()
    assert bool(result.values[3, 1, 1])


def test_cluster_filter_drops_small_components():
    values = np.zeros((1, 10, 10))
    values[0, 0, 0] = 1  # lone pixel
    values[0, 5:8, 5:8] = 1  # 9-pixel block
    result = cluster_filter(mask_from(values), min_pixels=5)
    assert not result.values[0, 0, 0]
    assert result.values[0, 5:8, 5:8].all()


def test_linearity_separates_lines_from_blobs():
    line = np.zeros((20, 20), dtype=bool)
    np.fill_diagonal(line, True)
    blob = np.zeros((20, 20), dtype=bool)
    blob[5:12, 5:12] = True
    assert linearity_score(line) > 0.9
    assert linearity_score(blob) < 0.3
