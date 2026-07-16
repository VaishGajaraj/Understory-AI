"""GUNW retrieval and coherence-layer extraction.

The archive is hundreds of terabytes; the long-run design is in-region S3
streaming of just the coherence layer. v0 is deliberately simpler and correct:
fetch the granule once into a local content-addressed cache (HTTPS + Earthdata
netrc auth), then read the coherence dataset out of the HDF5. The extraction
walks the file rather than hardcoding one path, because the BETA/PROVISIONAL/
validated product trees are still shifting.
"""

from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
import xarray as xr

from understory_core.discovery import GunwPair

logger = logging.getLogger(__name__)


def _as_group(node) -> h5py.Group:
    from typing import cast

    return cast(h5py.Group, node)


def _read(node) -> np.ndarray:
    from typing import cast

    return np.asarray(cast(h5py.Dataset, node)[...])


# Dataset names as published in the NISAR L2 GUNW product tree.
COHERENCE_DATASET = "coherenceMagnitude"
X_COORDS = "xCoordinates"
Y_COORDS = "yCoordinates"
PROJECTION = "projection"


def extract_coherence(
    source: GunwPair | str | Path,
    cache_dir: Path | None = None,
) -> xr.DataArray:
    """Return the geocoded coherence raster for one GUNW granule.

    ``source`` may be a GunwPair (fetched via its HTTPS URL into ``cache_dir``)
    or a path to an already-local HDF5 file.

    Output: 2-D DataArray (y, x) named ``coherence``, float32 in [0, 1], with
    ``crs`` (EPSG string) and pair metadata attached as attrs.
    """
    if isinstance(source, GunwPair):
        path = fetch_granule(source, cache_dir or Path("data/scratch/granules"))
        attrs = {
            "granule_id": source.granule_id,
            "track": source.track,
            "frame": source.frame,
            "reference_start": source.reference_start.isoformat(),
            "secondary_start": source.secondary_start.isoformat(),
            "calibration_tier": source.calibration_tier,
        }
    else:
        path = Path(source)
        attrs = {"granule_id": path.stem}

    with h5py.File(path, "r") as h5:
        dataset_path = _find_coherence_dataset(h5)
        values = _read(h5[dataset_path]).astype(np.float32)
        x, y = _find_coordinates(h5, dataset_path, values.shape)
        epsg = _find_epsg(h5, dataset_path)

    da = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={"y": y, "x": x},
        name="coherence",
        attrs={**attrs, "crs": f"EPSG:{epsg}" if epsg else "unknown", "source_path": dataset_path},
    )
    return da


def fetch_granule(pair: GunwPair, cache_dir: Path) -> Path:
    """Download a granule to the local cache (no-op when already present).

    Uses HTTPS with NASA Earthdata credentials from ~/.netrc (see
    docs/DATA_ACCESS.md). requests follows the URS redirect dance natively.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{pair.granule_id}.h5"
    if target.exists() and target.stat().st_size > 0:
        return target

    import requests

    logger.info("fetching %s", pair.granule_id)
    with requests.get(pair.url, stream=True, timeout=120) as response:
        if response.status_code in (401, 403):
            raise PermissionError(
                f"Earthdata authorization failed for {pair.url} — put NASA Earthdata "
                "credentials in ~/.netrc (machine urs.earthdata.nasa.gov ...); "
                "see docs/DATA_ACCESS.md"
            )
        response.raise_for_status()
        partial = target.with_suffix(".h5.part")
        with open(partial, "wb") as f:
            for chunk in response.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        partial.rename(target)
    return target


def _find_coherence_dataset(h5: h5py.File) -> str:
    """Locate the coherence dataset, preferring the unwrapped-interferogram one."""
    candidates: list[str] = []

    def visit(name: str, obj) -> None:
        if isinstance(obj, h5py.Dataset) and name.rsplit("/", 1)[-1] == COHERENCE_DATASET:
            candidates.append(name)

    h5.visititems(visit)
    if not candidates:
        raise KeyError(
            f"no '{COHERENCE_DATASET}' dataset found — not a GUNW product, or the "
            "product tree changed (record the new layout in docs/ARCHIVE_STATUS.md)"
        )
    unwrapped = [c for c in candidates if "nwrapped" in c]
    return (unwrapped or candidates)[0]


def _find_coordinates(
    h5: h5py.File, dataset_path: str, shape: tuple[int, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Find x/y coordinate vectors matching the raster shape, walking up from
    the dataset's group toward the root."""
    n_rows, n_cols = shape
    for group_path in _ancestor_groups(dataset_path):
        group = _as_group(h5[group_path]) if group_path else h5
        if X_COORDS in group and Y_COORDS in group:
            x = _read(group[X_COORDS])
            y = _read(group[Y_COORDS])
            if len(x) == n_cols and len(y) == n_rows:
                return x, y
    raise KeyError(f"no {X_COORDS}/{Y_COORDS} matching shape {shape} found near {dataset_path}")


def _find_epsg(h5: h5py.File, dataset_path: str) -> int | None:
    """Find the EPSG code from the nearest 'projection' dataset, if present."""
    for group_path in _ancestor_groups(dataset_path):
        group = _as_group(h5[group_path]) if group_path else h5
        if PROJECTION in group:
            projection = group[PROJECTION]
            epsg = projection.attrs.get("epsg_code")
            if epsg is not None:
                return int(epsg)
            try:
                return int(_read(projection).item())
            except (TypeError, ValueError):
                return None
    return None


def _ancestor_groups(dataset_path: str) -> list[str]:
    """Group paths from the dataset's parent up to the root ('' = root)."""
    parts = dataset_path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(len(parts), -1, -1)]
