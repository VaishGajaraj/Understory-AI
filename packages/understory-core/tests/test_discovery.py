from datetime import datetime

from understory_core.discovery import (
    GunwPair,
    group_by_frame,
    pair_from_asf_properties,
    parse_pair_times,
    single_cycle_pairs,
    summarize_coverage,
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


def test_coverage_summary_is_json_ready_and_recommends_longest_frame():
    pairs = [
        make_pair(10, 5, "2026-01-01T09:00", "2026-01-13T09:00"),
        make_pair(10, 5, "2026-01-13T09:00", "2026-01-25T09:00"),
        make_pair(11, 8, "2026-01-01T09:00", "2026-01-13T09:00"),
        make_pair(11, 8, "2026-01-01T09:00", "2026-01-25T09:00"),  # not 12-day
    ]
    summary = summarize_coverage(pairs, "provisional")

    assert summary["schema_version"] == "1"
    assert summary["pair_count"] == 4
    assert summary["single_cycle_pair_count"] == 3
    assert summary["recommended_frame"]["track"] == 10
    assert summary["recommended_frame"]["pair_count"] == 2
    assert len(summary["recommended_frame"]["granule_ids"]) == 2


# --- catalog checksum -------------------------------------------------------
#
# Settled against the live archive 2026-07-27: CMR publishes a per-file MD5 for
# NISAR GUNW, but asf_search's flat `md5sum` property is None for these
# granules. Reading only `md5sum` throws away a digest the archive does publish
# and silently downgrades every download to the unverified path.


def _props(**extra) -> dict:
    base = {
        "sceneName": (
            "NISAR_L2_PR_GUNW_009_155_D_094_010_2000_SH_20260107T231703_20260107T231737_"
            "20260119T231703_20260119T231738_X05010_N_P_J_001"
        ),
        "pathNumber": 155,
        "frameNumber": 94,
        "flightDirection": "DESCENDING",
        "url": "https://example.invalid/g.h5",
    }
    base.update(extra)
    return base


def test_md5_read_from_the_per_file_checksum_when_the_flat_property_is_none():
    pair = pair_from_asf_properties(
        _props(
            md5sum=None,
            archiveAndDistributionInformation=[
                {"Name": "g_LATLON.png", "Checksum": {"Value": "aaa", "Algorithm": "MD5"}},
                {"Name": "g.h5", "Checksum": {"Value": "499bb59ac8e2622f", "Algorithm": "MD5"}},
            ],
        ),
        "provisional",
    )
    assert pair.md5 == "499bb59ac8e2622f", "must pick the HDF5's digest, not a browse image's"


def test_flat_md5sum_property_still_wins_when_present():
    pair = pair_from_asf_properties(_props(md5sum="flat-digest"), "provisional")
    assert pair.md5 == "flat-digest"


def test_missing_checksum_is_none_not_an_error():
    assert pair_from_asf_properties(_props(), "beta").md5 is None
    assert (
        pair_from_asf_properties(_props(archiveAndDistributionInformation="?"), "beta").md5 is None
    )
    assert (
        pair_from_asf_properties(
            _props(
                archiveAndDistributionInformation=[
                    {"Name": "g.h5", "Checksum": {"Algorithm": "SHA256", "Value": "x"}}
                ]
            ),
            "beta",
        ).md5
        is None
    ), "a non-MD5 algorithm must not be passed off as an MD5"


def test_baseline_rounds_across_day_boundary():
    """A 12-day repeat whose secondary starts minutes earlier in the day
    truncates to 11 with timedelta.days — the archive does this constantly,
    and truncation silently discarded half the usable pairs."""
    pair = make_pair(89, 175, "2026-06-20T23:50:00", "2026-07-02T23:35:00")
    assert (pair.secondary_start - pair.reference_start).days == 11  # the trap
    assert pair.temporal_baseline_days == 12  # the fix


def test_dedupe_prefers_full_coverage_then_latest():
    from understory_core.discovery import dedupe_pairs

    def variant(granule_id: str):
        p = make_pair(89, 175, "2026-06-20T09:00", "2026-07-02T09:00")
        object.__setattr__(p, "granule_id", granule_id)
        return p

    partial = variant("NISAR_L2_PR_GUNW_x_X05010_N_P_J_001")
    full_old = variant("NISAR_L2_PR_GUNW_x_X05010_N_F_J_001")
    full_new = variant("NISAR_L2_PR_GUNW_x_X05010_N_F_J_002")
    other_pair = make_pair(89, 175, "2026-07-02T09:00", "2026-07-14T09:00")

    kept = dedupe_pairs([partial, full_old, full_new, other_pair])
    assert len(kept) == 2
    assert kept[0].granule_id == "NISAR_L2_PR_GUNW_x_X05010_N_F_J_002"
    assert kept[1] == other_pair
