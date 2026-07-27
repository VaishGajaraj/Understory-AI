"""Guards on CoherenceStack.build inputs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr
from understory_core import stack as stack_module
from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.stack import (
    CoherenceStack,
    GridSpec,
    _align_to,
    _grids_match,
    _marker_path,
)

AOI = AreaOfInterest(
    name="t",
    geometry={
        "type": "Polygon",
        "coordinates": [
            [[-55.0, -7.0], [-54.9, -7.0], [-54.9, -6.9], [-55.0, -6.9], [-55.0, -7.0]]
        ],
    },
)


def pair(frame: int = 10, tier: str = "beta") -> GunwPair:
    return GunwPair(
        granule_id=f"G-{frame}-{tier}",
        track=99,
        frame=frame,
        flight_direction="DESCENDING",
        reference_start=datetime(2026, 1, 7),
        secondary_start=datetime(2026, 1, 19),
        url="https://example.invalid/g.h5",
        s3_url=None,
        calibration_tier=tier,
    )


def test_zero_pairs_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="zero pairs"):
        CoherenceStack.build(AOI, [], tmp_path / "s.zarr")


def test_mixed_frame_groups_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="frame groups"):
        CoherenceStack.build(AOI, [pair(frame=10), pair(frame=11)], tmp_path / "s.zarr")


def test_mixed_calibration_tiers_are_rejected(tmp_path):
    """Processor differences between tiers make a mixed stack invalid, not merely caveated."""
    pairs = [pair(tier="beta"), pair(tier="provisional")]
    with pytest.raises(ValueError, match="calibration tiers"):
        CoherenceStack.build(AOI, pairs, tmp_path / "s.zarr")


# --- regressions found by pre-push review, each reproduced before fixing -----


def raster(y, x, fill: float = 1.0) -> xr.DataArray:
    return xr.DataArray(
        np.full((len(y), len(x)), fill, np.float32),
        dims=("y", "x"),
        coords={"y": np.asarray(y, float), "x": np.asarray(x, float)},
        name="coherence",
        attrs={"crs": "EPSG:32721"},
    )


# A grid inside AOI's bounds, north-up like a real geocoded product.
AOI_Y = np.linspace(-6.905, -6.995, 5)
AOI_X = np.linspace(-54.995, -54.905, 5)


def build_with(pairs, tmp_path, rasters=None):
    """Run build against synthetic rasters instead of real granules."""
    supplied = iter(rasters) if rasters is not None else None

    def fake_extract(source, cache_dir=None):
        if supplied is not None:
            return next(supplied)
        return raster(AOI_Y, AOI_X)

    with patch.object(stack_module, "extract_coherence", fake_extract):
        return CoherenceStack.build(AOI, pairs, tmp_path / "s.zarr")


def dated_pair(ref_day: int, sec_day: int) -> GunwPair:
    base = datetime(2026, 1, 1)
    return GunwPair(
        granule_id=f"G{ref_day}-{sec_day}",
        track=1,
        frame=2,
        flight_direction="DESCENDING",
        reference_start=base + timedelta(days=ref_day),
        secondary_start=base + timedelta(days=sec_day),
        url="u",
        s3_url=None,
        calibration_tier="beta",
    )


def test_attrs_survive_appending_more_than_one_pair(tmp_path):
    """Appending replaces group attrs, so they must be re-stamped every write.

    calibration_tier living only in a one-pair stack would silently drop the
    field the re-validation gate depends on.
    """
    pairs = [dated_pair(0, 12), dated_pair(12, 24), dated_pair(24, 36)]
    stack = build_with(pairs, tmp_path)
    assert stack.dataset.attrs["calibration_tier"] == "beta"
    assert stack.dataset.attrs["crs"] == "EPSG:32721"
    assert stack.dataset.attrs["track"] == 1


def test_time_axis_is_monotonic_under_mixed_temporal_baselines(tmp_path):
    """Ordering must follow the midpoint written, not reference_start.

    The rolling baseline shifts positionally, so a scrambled time index means
    the trailing window is not trailing in time -- and nothing would raise.
    """
    pairs = [dated_pair(0, 48), dated_pair(12, 24), dated_pair(24, 36)]
    times = build_with(pairs, tmp_path).dataset.time.values
    assert np.all(np.diff(times) > np.timedelta64(0, "ns")), [str(t)[:10] for t in times]


def test_duplicate_midpoints_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="share midpoint"):
        build_with([dated_pair(0, 12), dated_pair(0, 12)], tmp_path)


def test_edge_granule_on_the_same_lattice_is_reindexed_not_rejected():
    """Two granules on one lattice with different extents differ by whole
    pixels; checking absolute origin offset rejected exactly the case the
    reindex path exists for."""
    grid = GridSpec.of(raster(np.arange(10), np.arange(10)))
    shifted = raster(np.arange(1, 11), np.arange(1, 11))
    aligned = _align_to(shifted, grid, "G1")
    assert aligned.shape == (10, 10)
    assert np.isnan(aligned.values).any()  # non-overlapping edge is NaN-filled


def test_off_lattice_granule_is_rejected():
    grid = GridSpec.of(raster(np.arange(10), np.arange(10)))
    half_pixel = raster(np.arange(10) + 0.5, np.arange(10) + 0.5)
    with pytest.raises(ValueError, match="off the stack grid"):
        _align_to(half_pixel, grid, "G2")


def test_anisotropic_grid_uses_per_dimension_spacing():
    """A y misregistration must be judged against y spacing, not x spacing.

    With one shared tolerance a 0.9-pixel y shift passed the check and was then
    snapped by nearest-neighbour, duplicating a row with no warning.
    """
    grid = GridSpec.of(raster(np.arange(20), np.arange(0, 2000, 100)))
    misregistered = raster(np.arange(20) + 0.9, np.arange(0, 2000, 100))
    with pytest.raises(ValueError, match="off the stack grid in y"):
        _align_to(misregistered, grid, "G3")


def test_single_column_grid_does_not_crash():
    """A one-pixel-wide clip has no measurable spacing; that is not an error."""
    grid = GridSpec.of(raster(np.arange(5), [0.0]))
    assert _align_to(raster(np.arange(4), [0.0]), grid, "G4").shape == (5, 1)
    assert GridSpec.of(raster(np.arange(5), [0.0])).spacing("x") == 0.0


def test_identical_grid_takes_the_fast_path():
    grid = GridSpec.of(raster(np.arange(10), np.arange(10)))
    assert _grids_match(raster(np.arange(10), np.arange(10)), grid)
    assert not _grids_match(raster(np.arange(9), np.arange(10)), grid)


# --- idempotent resume ------------------------------------------------------


def build_counting(pairs, store):
    """Build against a constant synthetic raster, recording which pairs were
    actually extracted so a resume can be shown to skip what the store holds."""
    extracted: list[str] = []

    def fake_extract(source, cache_dir=None):
        extracted.append(source.granule_id)
        return raster(AOI_Y, AOI_X)

    with patch.object(stack_module, "extract_coherence", fake_extract):
        stack = CoherenceStack.build(AOI, pairs, store)
    return stack, extracted


def framed_pair(ref_day: int, sec_day: int, *, frame: int = 2, tier: str = "beta") -> GunwPair:
    base = datetime(2026, 1, 1)
    return GunwPair(
        granule_id=f"G{ref_day}-{sec_day}-{frame}-{tier}",
        track=1,
        frame=frame,
        flight_direction="DESCENDING",
        reference_start=base + timedelta(days=ref_day),
        secondary_start=base + timedelta(days=sec_day),
        url="u",
        s3_url=None,
        calibration_tier=tier,
    )


def test_resume_appends_only_the_missing_tail(tmp_path):
    store = tmp_path / "s.zarr"
    pairs = [dated_pair(0, 12), dated_pair(12, 24), dated_pair(24, 36)]

    _, first = build_counting(pairs[:2], store)
    assert first == ["G0-12", "G12-24"]

    stack, second = build_counting(pairs, store)
    # Only the third granule is extracted; the first two are already stored.
    assert second == ["G24-36"]
    times = stack.dataset.time.values
    assert len(times) == 3
    assert np.all(np.diff(times) > np.timedelta64(0, "ns"))


def test_rerunning_a_complete_build_is_a_noop(tmp_path):
    store = tmp_path / "s.zarr"
    pairs = [dated_pair(0, 12), dated_pair(12, 24), dated_pair(24, 36)]

    build_counting(pairs, store)
    stack, again = build_counting(pairs, store)

    assert again == []  # nothing re-extracted, nothing appended
    assert len(stack.dataset.time.values) == 3  # no duplicates


def test_resume_refuses_a_divergent_pair_list(tmp_path):
    store = tmp_path / "s.zarr"
    build_counting([dated_pair(0, 12), dated_pair(12, 24)], store)

    # A different leading pair (midpoint day 8, not day 6) — the store was built
    # from another set, so resuming would scramble the time axis.
    divergent = [dated_pair(2, 14), dated_pair(12, 24), dated_pair(24, 36)]
    with pytest.raises(ValueError, match="do not match the leading pairs"):
        build_counting(divergent, store)


def test_resume_refuses_when_marker_and_store_disagree(tmp_path):
    """A marker recording fewer timesteps than the store physically holds is the
    fingerprint of an interrupted, possibly torn append — refuse, don't guess."""
    store = tmp_path / "s.zarr"
    pairs = [dated_pair(0, 12), dated_pair(12, 24), dated_pair(24, 36)]
    build_counting(pairs[:2], store)  # marker: committed 2, store: 2 timesteps

    marker = json.loads(_marker_path(store).read_text())
    marker["committed"] = 1
    marker["midpoints"] = marker["midpoints"][:1]
    _marker_path(store).write_text(json.dumps(marker))

    with pytest.raises(ValueError, match="indeterminate"):
        build_counting(pairs, store)


def test_store_without_a_marker_is_refused(tmp_path):
    store = tmp_path / "s.zarr"
    pairs = [dated_pair(0, 12), dated_pair(12, 24)]
    build_counting(pairs, store)
    _marker_path(store).unlink()

    with pytest.raises(ValueError, match="no build marker"):
        build_counting(pairs, store)


def test_resume_refuses_a_different_tier(tmp_path):
    store = tmp_path / "s.zarr"
    build_counting([framed_pair(0, 12, tier="beta"), framed_pair(12, 24, tier="beta")], store)

    provisional = [
        framed_pair(0, 12, tier="provisional"),
        framed_pair(12, 24, tier="provisional"),
        framed_pair(24, 36, tier="provisional"),
    ]
    with pytest.raises(ValueError, match="tier"):
        build_counting(provisional, store)


def test_resume_refuses_a_different_frame(tmp_path):
    store = tmp_path / "s.zarr"
    build_counting([framed_pair(0, 12, frame=2), framed_pair(12, 24, frame=2)], store)

    other_frame = [
        framed_pair(0, 12, frame=9),
        framed_pair(12, 24, frame=9),
        framed_pair(24, 36, frame=9),
    ]
    with pytest.raises(ValueError, match="frame"):
        build_counting(other_frame, store)


def test_resume_refuses_a_torn_append_with_an_actionable_error(tmp_path):
    """A kill between the time and coherence shape writes leaves the two arrays
    disagreeing. open_zarr then fails with 'conflicting sizes' before any
    resume check could run, so the guard was dead code for exactly the state it
    was built to catch — the operator saw an internal xarray error with no
    recovery guidance."""
    import json

    pairs = [dated_pair(0, 12), dated_pair(12, 24), dated_pair(24, 36)]
    build_with(pairs[:2], tmp_path)
    store = tmp_path / "s.zarr"

    # Simulate the torn state: bump the coherence array's shape as an
    # interrupted third append would, leaving time (and the marker) at 2.
    meta_path = store / "coherence" / "zarr.json"
    meta = json.loads(meta_path.read_text())
    meta["shape"][0] = 3
    meta_path.write_text(json.dumps(meta))

    with pytest.raises(ValueError, match="torn.*Delete the store and rebuild"):
        build_with(pairs, tmp_path)


def test_resume_refuses_a_marker_with_a_scalar_frame_key(tmp_path):
    """A corrupted marker holding a scalar frame_key crashed with TypeError
    instead of the actionable refusal every other malformed state gets."""
    import json

    pairs = [dated_pair(0, 12), dated_pair(12, 24)]
    build_with(pairs, tmp_path)
    marker_path = tmp_path / "s.zarr.build.json"
    marker = json.loads(marker_path.read_text())
    marker["frame_key"] = 12
    marker_path.write_text(json.dumps(marker))

    with pytest.raises(ValueError, match="one stack per frame group"):
        build_with(pairs, tmp_path)
