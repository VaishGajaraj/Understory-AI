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
from understory_core.download import RetryPolicy
from understory_core.ingest import extract_coherence, fetch_granule, fetch_granules
from understory_core.manifest import GranuleRecord, IngestManifest, utcnow

GRID_ROOT = "science/LSAR/GUNW/grids/frequencyA"

# Sub-millisecond backoff so any retry path runs effectively instantly.
FAST = RetryPolicy(max_attempts=4, initial_backoff_s=0.0001, max_backoff_s=0.001, jitter=0.0)


def gunw_pair(url: str, granule_id: str = "G-download", size_bytes: int | None = None) -> GunwPair:
    return GunwPair(
        granule_id=granule_id,
        track=99,
        frame=76,
        flight_direction="DESCENDING",
        reference_start=datetime(2025, 11, 5),
        secondary_start=datetime(2025, 11, 17),
        url=url,
        s3_url=None,
        calibration_tier="beta",
        size_bytes=size_bytes,
    )


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
    # The new cache contract is "recorded as complete AND intact", not merely a
    # file on disk — so a cache hit needs a manifest row, which a real fetch
    # writes only after a verified download. Seed one pointing at the fixture.
    IngestManifest.for_cache(tmp_path).record(
        GranuleRecord(
            granule_id=pair.granule_id,
            calibration_tier=pair.calibration_tier,
            track=pair.track,
            frame=pair.frame,
            reference_start=pair.reference_start,
            secondary_start=pair.secondary_start,
            path=cached,
            size_bytes=cached.stat().st_size,
            md5=None,
            checksum_verified=False,
            completed_at=utcnow(),
        )
    )
    # url is unreachable by construction — this only passes via the cache
    result = fetch_granule(pair, tmp_path)
    assert result == cached
    da = extract_coherence(pair, cache_dir=tmp_path)
    assert da.attrs["granule_id"] == "cached-granule"
    assert da.attrs["calibration_tier"] == "beta"


def test_fetch_downloads_records_and_reads(http_server, tmp_path):
    """The whole ingest path end to end: download over HTTP, record in the
    manifest, then read coherence out of the fetched HDF5."""
    source = tmp_path / "source.h5"
    make_gunw_fixture(source)
    http_server.body = source.read_bytes()
    pair = gunw_pair(http_server.url, size_bytes=len(http_server.body))

    cache = tmp_path / "cache"
    path = fetch_granule(pair, cache, policy=FAST)

    assert path == cache / "G-download.h5"
    assert path.read_bytes() == http_server.body
    record = IngestManifest.for_cache(cache).get("G-download")
    assert record is not None
    assert record.size_bytes == len(http_server.body)
    assert extract_coherence(pair, cache_dir=cache).attrs["granule_id"] == "G-download"


def test_second_fetch_hits_manifest_not_network(http_server, tmp_path):
    source = tmp_path / "source.h5"
    make_gunw_fixture(source)
    http_server.body = source.read_bytes()
    pair = gunw_pair(http_server.url)
    cache = tmp_path / "cache"

    fetch_granule(pair, cache, policy=FAST)
    assert len(http_server.requests) == 1

    # Same granule again (the cross-AOI redundant-fetch case): the manifest
    # answers, so the server is never touched a second time.
    http_server.script = ["403", "403", "403", "403"]  # would fail if contacted
    again = fetch_granule(pair, cache, policy=FAST)
    assert again == cache / "G-download.h5"
    assert len(http_server.requests) == 1


def test_corrupt_cache_is_refetched_not_trusted(http_server, tmp_path):
    """A cached file truncated after the fact must be re-fetched, not served —
    the defect the old exists()-and-size check could not catch."""
    source = tmp_path / "source.h5"
    make_gunw_fixture(source)
    http_server.body = source.read_bytes()
    pair = gunw_pair(http_server.url)
    cache = tmp_path / "cache"

    path = fetch_granule(pair, cache, policy=FAST)
    assert len(http_server.requests) == 1

    # Corrupt the cached file: right name, wrong length.
    path.write_bytes(b"\x00" * 10)
    restored = fetch_granule(pair, cache, policy=FAST)
    assert restored.read_bytes() == http_server.body
    assert len(http_server.requests) == 2  # it really did re-download


def test_fetch_granules_deduplicates_by_identity(http_server, tmp_path):
    source = tmp_path / "source.h5"
    make_gunw_fixture(source)
    http_server.body = source.read_bytes()
    cache = tmp_path / "cache"

    # Two references to the *same* granule id — as several overlapping AOIs
    # would produce — must download once.
    pairs = [
        gunw_pair(http_server.url, granule_id="G-shared"),
        gunw_pair(http_server.url, granule_id="G-shared"),
    ]
    paths = fetch_granules(pairs, cache, policy=FAST)

    assert set(paths) == {"G-shared"}
    assert len(http_server.requests) == 1


def test_fetch_granules_bounded_concurrency(http_server, tmp_path):
    """The concurrent path fetches distinct granules and records them all; the
    WAL manifest absorbs the concurrent writes."""
    source = tmp_path / "source.h5"
    make_gunw_fixture(source)
    http_server.body = source.read_bytes()
    cache = tmp_path / "cache"

    pairs = [gunw_pair(http_server.url, granule_id=f"G-{i}") for i in range(4)]
    paths = fetch_granules(pairs, cache, policy=FAST, max_workers=3)

    assert set(paths) == {"G-0", "G-1", "G-2", "G-3"}
    manifest = IngestManifest.for_cache(cache)
    assert len(manifest) == 4
    assert all(p.read_bytes() == http_server.body for p in paths.values())
