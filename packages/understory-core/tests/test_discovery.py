from datetime import datetime

from understory_core.discovery import GranuleRef, pair_consecutive_passes


def granule(track: int, frame: int, when: str) -> GranuleRef:
    return GranuleRef(
        granule_id=f"NISAR_L2_GUNW_{track}_{frame}_{when}",
        track=track,
        frame=frame,
        acquisition=datetime.fromisoformat(when),
        product_type="GUNW",
        url="s3://example/granule.h5",
    )


def test_pairs_consecutive_12_day_passes():
    granules = [
        granule(12, 100, "2026-01-01T09:00"),
        granule(12, 100, "2026-01-13T09:00"),
        granule(12, 100, "2026-01-25T09:00"),
    ]
    pairs = pair_consecutive_passes(granules)
    assert len(pairs) == 2
    assert all(p.temporal_baseline_days == 12 for p in pairs)


def test_skips_gaps_longer_than_one_cycle():
    granules = [
        granule(12, 100, "2026-01-01T09:00"),
        # missed acquisition on 2026-01-13
        granule(12, 100, "2026-01-25T09:00"),
    ]
    assert pair_consecutive_passes(granules) == []


def test_does_not_pair_across_frames():
    granules = [
        granule(12, 100, "2026-01-01T09:00"),
        granule(12, 101, "2026-01-13T09:00"),
    ]
    assert pair_consecutive_passes(granules) == []
