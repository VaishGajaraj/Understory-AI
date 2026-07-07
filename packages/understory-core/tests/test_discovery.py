from datetime import datetime

from understory_core.discovery import (
    GunwPair,
    group_by_frame,
    pair_from_asf_properties,
    parse_pair_times,
    single_cycle_pairs,
)

# A real scene name from the live BETA archive (first data contact, July 2026).
REAL_SCENE = (
    "NISAR_L2_PR_GUNW_009_155_D_094_010_2000_SH_"
    "20260107T231703_20260107T231737_20260119T231703_20260119T231738_"
    "X05010_N_P_J_001"
)


def make_pair(track: int, frame: int, ref: str, sec: str) -> GunwPair:
    return GunwPair(
        granule_id=f"test-{track}-{frame}-{ref}",
        track=track,
        frame=frame,
        flight_direction="ASCENDING",
        reference_start=datetime.fromisoformat(ref),
        secondary_start=datetime.fromisoformat(sec),
        url="https://example/granule.h5",
        s3_url=None,
        calibration_tier="beta",
    )


def test_parse_pair_times_from_real_scene_name():
    reference, secondary = parse_pair_times(REAL_SCENE)
    assert reference == datetime(2026, 1, 7, 23, 17, 3)
    assert secondary == datetime(2026, 1, 19, 23, 17, 3)
    assert (secondary - reference).days == 12


def test_pair_from_asf_properties():
    properties = {
        "sceneName": REAL_SCENE,
        "pathNumber": 155,
        "frameNumber": 94,
        "flightDirection": "DESCENDING",
        "url": "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/x.h5",
        "s3Urls": [
            "s3://bucket/browse.png",
            "s3://bucket/NISAR_L2_PR_GUNW_....h5",
        ],
    }
    pair = pair_from_asf_properties(properties, tier="beta")
    assert pair.track == 155
    assert pair.frame == 94
    assert pair.temporal_baseline_days == 12
    assert pair.s3_url is not None and pair.s3_url.endswith(".h5")
    assert pair.calibration_tier == "beta"


def test_single_cycle_pairs_drops_long_baselines():
    pairs = [
        make_pair(10, 5, "2026-01-01T09:00", "2026-01-13T09:00"),  # 12 days
        make_pair(10, 5, "2026-01-01T09:00", "2026-01-25T09:00"),  # 24 days
    ]
    kept = single_cycle_pairs(pairs)
    assert len(kept) == 1
    assert kept[0].temporal_baseline_days == 12


def test_group_by_frame_separates_geometries():
    pairs = [
        make_pair(10, 5, "2026-01-13T09:00", "2026-01-25T09:00"),
        make_pair(10, 6, "2026-01-01T09:00", "2026-01-13T09:00"),
        make_pair(10, 5, "2026-01-01T09:00", "2026-01-13T09:00"),
    ]
    grouped = group_by_frame(pairs)
    assert set(grouped) == {(10, 5, "ASCENDING"), (10, 6, "ASCENDING")}
    frame_5 = grouped[(10, 5, "ASCENDING")]
    assert [p.reference_start.day for p in frame_5] == [1, 13]  # time-ordered
