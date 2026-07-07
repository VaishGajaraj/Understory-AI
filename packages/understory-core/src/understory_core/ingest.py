"""Granule retrieval and coherence-layer extraction.

The archive is hundreds of terabytes: the pipeline is designed to run in-region
with direct S3 access, streaming only the coherence layer out of each L2 HDF5
product. Downloading whole granules is the fallback, never the design.
"""

from __future__ import annotations

from pathlib import Path

import xarray as xr

from understory_core.discovery import InterferometricPair


def extract_coherence(
    pair: InterferometricPair,
    cache_dir: Path | None = None,
) -> xr.DataArray:
    """Return the geocoded coherence raster for one interferometric pair.

    Output: 2-D DataArray (y, x) named ``coherence``, float32 in [0, 1],
    with CRS and pair metadata (reference/secondary datetimes, track, frame)
    attached as attrs.
    """
    raise NotImplementedError(
        "v0: open the L2 GUNW HDF5 (h5py over fsspec/S3), read the coherence "
        "dataset and geocoding grid, wrap as a rioxarray DataArray"
    )
