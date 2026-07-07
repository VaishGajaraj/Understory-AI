"""Coherence time-series stack construction.

A CoherenceStack is the central data structure of the whole project: a
per-pixel time series of 12-day coherence values over an AOI, stored as a
Zarr-backed xarray Dataset with dims (time, y, x). Everything downstream —
baselines, detectors, scoring — consumes this.
"""

from __future__ import annotations

from pathlib import Path

import xarray as xr

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair


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
    ) -> CoherenceStack:
        """Extract coherence for each pair, clip to the AOI, align on a common
        grid, and stack along time (indexed by pair midpoint date).

        ``pairs`` must come from a single frame group (see
        ``discovery.group_by_frame``) — mixing geometries corrupts the
        per-pixel time series.
        """
        raise NotImplementedError(
            "v0: extract_coherence per pair (dask-parallel per tile), "
            "reproject-match to a common grid, concat along time, write Zarr"
        )

    @classmethod
    def open(cls, store: Path | str, aoi: AreaOfInterest) -> CoherenceStack:
        """Open an existing stack without recomputing."""
        return cls(xr.open_zarr(store), aoi)
