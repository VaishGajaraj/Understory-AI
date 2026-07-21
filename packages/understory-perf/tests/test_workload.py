"""Arrival models. These decide what the load test is actually testing."""

from __future__ import annotations

import pytest
from understory_perf.workload import (
    SECONDS_PER_DAY,
    aoi_backfill,
    build,
    cycle_burst,
    reprocess_backlog,
    steady_cycle,
)


def test_steady_cycle_covers_every_aoi_and_frame_group():
    load = steady_cycle(10, frame_groups=4)
    assert load.n_items == 40
    assert len({a.item.aoi for a in load.arrivals}) == 10
    assert len({a.item.frame_group for a in load.arrivals}) == 4


def test_steady_cycle_spreads_arrivals_across_the_whole_cycle():
    load = steady_cycle(10)
    assert load.arrivals[0].at_seconds == 0.0
    assert load.span_seconds == pytest.approx(load.deadline_seconds)


def test_burst_delivers_the_same_volume_far_faster():
    """The comparison the harness exists to make: same work, worse arrival rate."""
    steady = steady_cycle(10)
    burst = cycle_burst(10, burst_fraction=0.05)
    assert burst.n_items == steady.n_items
    assert burst.n_pairs == steady.n_pairs
    assert burst.deadline_seconds == steady.deadline_seconds
    assert burst.span_seconds == pytest.approx(steady.span_seconds * 0.05)


def test_reprocess_backlog_arrives_all_at_once():
    load = reprocess_backlog(5)
    assert {a.at_seconds for a in load.arrivals} == {0.0}
    assert load.deadline_seconds == 30 * SECONDS_PER_DAY


def test_reprocess_backlog_uses_a_full_year_of_history():
    load = reprocess_backlog(2, history_years=1.0)
    # ~30 single-cycle pairs per year on one track/frame.
    assert all(a.item.n_pairs == 30 for a in load.arrivals)


def test_backfill_depth_scales_with_history():
    assert reprocess_backlog(1, history_years=2.0).arrivals[0].item.n_pairs == 60
    assert aoi_backfill(1, history_years=0.5).arrivals[0].item.n_pairs == 15


def test_compression_scales_arrival_spacing_and_deadline_together():
    """Compression must not change utilization — only wall-clock convenience."""
    full = steady_cycle(5, compression=1.0)
    fast = steady_cycle(5, compression=1e-3)
    assert fast.deadline_seconds == pytest.approx(full.deadline_seconds * 1e-3)
    assert fast.span_seconds == pytest.approx(full.span_seconds * 1e-3)
    assert fast.seconds_per_model_day == pytest.approx(full.seconds_per_model_day * 1e-3)


def test_seeds_are_deterministic_across_builds():
    a = [x.item.seed for x in steady_cycle(6).arrivals]
    b = [x.item.seed for x in steady_cycle(6).arrivals]
    assert a == b


def test_unknown_shape_names_the_known_ones():
    with pytest.raises(KeyError, match="steady-cycle"):
        build("stampede", 3)
