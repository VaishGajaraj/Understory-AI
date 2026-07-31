from datetime import date, datetime

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import GunwPair
from understory_core.watch import WatchState, check

AOI = AreaOfInterest(
    name="watch-test",
    geometry={
        "type": "Polygon",
        "coordinates": [
            [[-55.0, -7.0], [-54.9, -7.0], [-54.9, -6.9], [-55.0, -6.9], [-55.0, -7.0]]
        ],
    },
)


def pair(granule_id: str, ref: str, sec: str) -> GunwPair:
    return GunwPair(
        granule_id=granule_id,
        track=99,
        frame=76,
        flight_direction="DESCENDING",
        reference_start=datetime.fromisoformat(ref),
        secondary_start=datetime.fromisoformat(sec),
        url="https://example/x.h5",
        s3_url=None,
        calibration_tier="beta",
    )


def test_first_run_reports_everything_then_goes_quiet():
    archive = [pair("g1", "2026-01-01T10:00", "2026-01-13T10:00")]
    state = WatchState(aoi_name="watch-test")

    new, state = check(
        AOI, state, start=date(2026, 1, 1), end=date(2026, 7, 1), search_fn=lambda *a, **k: archive
    )
    assert [p.granule_id for p in new] == ["g1"]

    new, state = check(
        AOI, state, start=date(2026, 1, 1), end=date(2026, 7, 1), search_fn=lambda *a, **k: archive
    )
    assert new == []
    assert state.seen_granules == {"g1"}


def test_new_acquisition_is_reported_once():
    first = [pair("g1", "2026-01-01T10:00", "2026-01-13T10:00")]
    later = first + [pair("g2", "2026-01-13T10:00", "2026-01-25T10:00")]
    state = WatchState(aoi_name="watch-test")

    _, state = check(
        AOI, state, start=date(2026, 1, 1), end=date(2026, 7, 1), search_fn=lambda *a, **k: first
    )
    new, state = check(
        AOI, state, start=date(2026, 1, 1), end=date(2026, 7, 1), search_fn=lambda *a, **k: later
    )
    assert [p.granule_id for p in new] == ["g2"]


def test_long_baseline_pairs_are_ignored():
    archive = [pair("g-long", "2026-01-01T10:00", "2026-01-25T10:00")]  # 24 days
    new, _ = check(
        AOI,
        WatchState(aoi_name="watch-test"),
        start=date(2026, 1, 1),
        end=date(2026, 7, 1),
        search_fn=lambda *a, **k: archive,
    )
    assert new == []


def test_state_roundtrip(tmp_path):
    state_path = tmp_path / "watch.json"
    state = WatchState(
        aoi_name="watch-test", seen_granules={"g1"}, last_checked="2026-07-01T00:00:00"
    )
    state.save(state_path)
    loaded = WatchState.load(state_path, "watch-test", "beta")
    assert loaded == state


def test_state_refuses_mismatched_watch(tmp_path):
    import pytest

    state_path = tmp_path / "watch.json"
    WatchState(aoi_name="other-aoi").save(state_path)
    with pytest.raises(ValueError, match="one state file per watch"):
        WatchState.load(state_path, "watch-test", "beta")
