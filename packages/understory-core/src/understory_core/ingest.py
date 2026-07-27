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
import requests
import xarray as xr

from understory_core.discovery import GunwPair
from understory_core.download import DEFAULT_RETRY_POLICY, RetryPolicy, download_file
from understory_core.manifest import GranuleRecord, IngestManifest, utcnow

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


def fetch_granule(
    pair: GunwPair,
    cache_dir: Path,
    *,
    manifest: IngestManifest | None = None,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    session: requests.Session | None = None,
) -> Path:
    """Fetch a granule to the local cache, idempotently and intact.

    Uses HTTPS with NASA Earthdata credentials from ~/.netrc (see
    docs/DATA_ACCESS.md); requests follows the URS redirect dance natively. The
    download itself (retry, backoff, resume, length/checksum checks) lives in
    ``understory_core.download``; this function is the cache-and-record layer
    around it.

    **The cache check is "recorded as complete AND intact", not "a file
    exists".** A granule is skipped only when the ingest manifest holds a row
    for it *and* the file that row names is still the right size on disk. That
    is the whole point of the state store: a bare ``.h5`` left behind by a
    killed process has no row, so it is re-fetched rather than trusted — closing
    the hole where ``exists() and st_size > 0`` accepted a truncated download
    forever. Because the row is keyed on ``granule_id`` and written only after a
    verified transfer, the same granule shared by several AOIs is downloaded
    once (see ``fetch_granules`` for deduplicating a whole pair list up front).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest or IngestManifest.for_cache(cache_dir)

    cached = manifest.intact(pair.granule_id)
    if cached is not None:
        return cached

    target = cache_dir / f"{pair.granule_id}.h5"
    logger.info("fetching %s", pair.granule_id)
    result = download_file(
        pair.url,
        target,
        expected_bytes=pair.size_bytes,
        expected_md5=pair.md5,
        policy=policy,
        session=session,
    )
    manifest.record(
        GranuleRecord(
            granule_id=pair.granule_id,
            calibration_tier=pair.calibration_tier,
            track=pair.track,
            frame=pair.frame,
            reference_start=pair.reference_start,
            secondary_start=pair.secondary_start,
            path=result.path,
            size_bytes=result.size_bytes,
            md5=result.md5,
            checksum_verified=result.checksum_verified,
            completed_at=utcnow(),
        )
    )
    return result.path


def fetch_granules(
    pairs: list[GunwPair],
    cache_dir: Path,
    *,
    manifest: IngestManifest | None = None,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    max_workers: int = 1,
) -> dict[str, Path]:
    """Fetch every distinct granule in ``pairs`` once, returning id -> path.

    At scale many AOIs share track/frame coverage, so a naive pass would fetch
    the same granule repeatedly. Deduplicating by ``granule_id`` before fetching
    collapses that; the manifest then also prevents re-fetching across separate
    calls and runs. ``max_workers`` bounds concurrency (the download path has no
    limit of its own); the default is sequential and deterministic, sharing one
    HTTP session, while a higher count gives each worker its own session and
    lets the WAL-mode manifest absorb concurrent writes.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest or IngestManifest.for_cache(cache_dir)
    unique: dict[str, GunwPair] = {}
    for pair in pairs:
        unique.setdefault(pair.granule_id, pair)

    if max_workers <= 1:
        with requests.Session() as shared:
            return {
                gid: fetch_granule(
                    pair, cache_dir, manifest=manifest, policy=policy, session=shared
                )
                for gid, pair in unique.items()
            }

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            gid: pool.submit(fetch_granule, pair, cache_dir, manifest=manifest, policy=policy)
            for gid, pair in unique.items()
        }
        return {gid: future.result() for gid, future in futures.items()}


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
