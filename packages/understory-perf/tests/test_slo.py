"""The ship / no-ship gate. If this logic is wrong the whole harness lies."""

from __future__ import annotations

import time

import pytest
from understory_perf import slo
from understory_perf.runner import RunResult
from understory_perf.workload import SECONDS_PER_DAY

CYCLE_SECONDS = 12 * SECONDS_PER_DAY


def make_result(
    *,
    n_items: int = 10,
    service_seconds: float = 100.0,
    queue_wait: float = 0.0,
    workers: int = 4,
    peak_rss_bytes: int = 2_000_000_000,
    n_failed: int = 0,
    rss_samples: int = 100,
) -> RunResult:
    timings = []
    for i in range(n_items):
        ok = i >= n_failed
        timings.append(
            {
                "aoi": f"aoi-{i}",
                "frame_group": i % 4,
                "stage": "detect",
                "n_pairs": 24,
                "input_bytes": 100_000_000,
                "available_at": 1000.0,
                "service_start": 1000.0 + queue_wait,
                "service_seconds": service_seconds,
                "peak_rss_bytes": peak_rss_bytes,
                "n_detections": 1,
                "n_tiles": 1,
                "ok": ok,
                "error": "" if ok else "MemoryError: out of memory",
                "extra": {},
            }
        )
    return RunResult(
        workload="test",
        description="",
        config={"workers": workers},
        height_px=1250,
        width_px=1250,
        timings=timings,
        peak_total_rss_bytes=peak_rss_bytes,
        rss_samples=rss_samples,
        makespan_seconds=service_seconds * n_items / workers,
        model_deadline_seconds=CYCLE_SECONDS,
        seconds_per_model_day=SECONDS_PER_DAY,
        n_failed=n_failed,
    )


def status_of(verdict: slo.SloVerdict, name: str) -> str:
    return next(o.status for o in verdict.objectives if o.name == name)


def test_comfortable_run_ships():
    verdict = slo.evaluate(make_result())
    assert verdict.shippable
    assert all(o.status == "PASS" for o in verdict.objectives)


def test_utilization_over_the_threshold_fails():
    # 10 items x 10 days of service on 4 workers vastly exceeds a 12-day cycle.
    verdict = slo.evaluate(make_result(service_seconds=10 * SECONDS_PER_DAY))
    assert status_of(verdict, "cycle-utilization") == "FAIL"
    assert not verdict.shippable


def test_utilization_note_calls_out_unbounded_backlog():
    verdict = slo.evaluate(make_result(service_seconds=10 * SECONDS_PER_DAY))
    note = next(o.note for o in verdict.objectives if o.name == "cycle-utilization")
    assert "backlog grows every cycle" in note


def test_latency_budget_is_derived_from_the_science_gate():
    # 5% of the 21-day lead-over-optical criterion, in hours.
    assert slo.MAX_ALERT_LATENCY_HOURS == 21 * 24 * 0.05


def test_service_time_beyond_the_lead_budget_fails_latency():
    verdict = slo.evaluate(make_result(service_seconds=30 * 3600))
    assert status_of(verdict, "alert-latency-p95") == "FAIL"


def test_memory_over_the_node_budget_fails():
    verdict = slo.evaluate(make_result(peak_rss_bytes=20_000_000_000))
    assert status_of(verdict, "peak-memory") == "FAIL"


def test_unsampled_memory_is_insufficient_data_not_a_pass():
    """Absent measurement must never read as a green light."""
    verdict = slo.evaluate(make_result(rss_samples=0))
    assert status_of(verdict, "peak-memory") == "INSUFFICIENT_DATA"
    assert verdict.shippable  # INSUFFICIENT_DATA does not block, but is visible


def test_any_failure_fails_the_failure_objective():
    verdict = slo.evaluate(make_result(n_failed=1))
    assert status_of(verdict, "failure-rate") == "FAIL"
    note = next(o.note for o in verdict.objectives if o.name == "failure-rate")
    assert "MemoryError" in note


def test_empty_run_reports_insufficient_data_everywhere():
    """A run with no work must never read as a comfortable pass."""
    verdict = slo.evaluate(make_result(n_items=0))
    assert {o.status for o in verdict.objectives} == {"INSUFFICIENT_DATA"}


def test_format_table_states_the_verdict():
    assert "DO NOT SHIP" in slo.format_table(slo.evaluate(make_result(n_failed=1)))
    assert "SHIP" in slo.format_table(slo.evaluate(make_result()))


def test_rss_sampler_starts_and_stops_cleanly():
    """Regression: naming the Event `self._stop` shadows threading.Thread._stop.

    The interpreter calls Thread._stop() during shutdown, so the shadowed name
    made every run die with "'Event' object is not callable" *after* completing
    all its work — the most expensive possible place to fail.
    """
    from understory_perf.runner import _RssSampler

    sampler = _RssSampler(interval=0.01)
    sampler.start()
    sampler.stop()
    assert not sampler.is_alive()
    assert sampler.samples >= 0


# --- compression must not distort capacity ---------------------------------
#
# Regression for the harness's worst bug: utilization divided *real* service
# seconds by a *compressed* deadline, overstating it by 1/compression (10,000x
# at the default). A scenario using 0.02% of a cycle reported 2.11 and failed
# its SLO. The latency objective had the mirror-image error, multiplying an
# already-elapsed measurement by the same factor.


def compressed(compression: float, **kwargs) -> RunResult:
    result = make_result(**kwargs)
    result.model_deadline_seconds = CYCLE_SECONDS * compression
    result.seconds_per_model_day = SECONDS_PER_DAY * compression
    return result


def test_utilization_is_invariant_to_compression():
    """Compressing arrivals makes the test cheap; it must not change capacity."""
    full = compressed(1.0).utilization
    fast = compressed(1e-4).utilization
    assert full is not None and fast is not None
    assert fast == pytest.approx(full, rel=1e-9)


def test_utilization_matches_the_hand_calculation():
    # 10 items x 100 s of service, 4 workers, one 12-day cycle.
    result = compressed(1e-4, n_items=10, service_seconds=100.0, workers=4)
    assert result.utilization == pytest.approx(1000.0 / (CYCLE_SECONDS * 4))


def test_burst_utilization_reports_the_compressed_window_separately():
    """The stress figure stays available — it just is not the capacity number."""
    result = compressed(1e-4, n_items=10, service_seconds=100.0, workers=4)
    utilization = result.utilization
    assert utilization is not None
    assert result.burst_utilization == pytest.approx(utilization / 1e-4)


def test_latency_objective_does_not_inflate_by_compression():
    """A 37 s service time is 37 s, not 37 s x 10,000."""
    result = compressed(1e-4, n_items=10, service_seconds=37.0, queue_wait=180.0)
    verdict = slo.evaluate(result)
    objective = next(o for o in verdict.objectives if o.name == "alert-latency-p95")
    assert objective.status == "PASS"
    assert objective.observed.startswith("0.010")  # 37 s = 0.0103 h


def test_latency_note_surfaces_the_burst_figure():
    result = compressed(1e-4, n_items=10, service_seconds=37.0, queue_wait=180.0)
    note = next(o.note for o in slo.evaluate(result).objectives if o.name == "alert-latency-p95")
    assert "compressed arrival rate" in note


def test_a_realistic_cycle_of_work_is_nowhere_near_saturating_a_cycle():
    """24 frame groups at ~37 s each is 0.02% of a 12-day cycle on 4 workers."""
    result = compressed(1e-4, n_items=24, service_seconds=37.0, workers=4)
    assert result.utilization is not None
    assert result.utilization < 0.001
    assert slo.evaluate(result).shippable


# --- metric defects found by pre-push review, each reproduced before fixing ---


def test_percentile_is_not_just_the_maximum_at_realistic_n():
    """Nearest-rank returned max for p99 at every n <= 51 and p95 at n <= 11.

    Every shipped latency_p99 was literally latency_max, and the alert-latency
    SLO was gating on the worst single item rather than a percentile.
    """
    import numpy as np

    result = make_result()
    for n in (8, 12, 24, 51):
        values = sorted(float(v) for v in range(n))
        for fraction in (0.5, 0.95, 0.99):
            got = result.percentile(values, fraction)
            assert got == pytest.approx(float(np.percentile(values, fraction * 100)))
        assert result.percentile(values, 0.99) != max(values) or n < 3


def test_percentile_handles_degenerate_inputs():
    result = make_result()
    assert result.percentile([], 0.95) is None
    assert result.percentile([4.0], 0.95) == 4.0
    assert result.percentile([1.0, 3.0], 0.5) == pytest.approx(2.0)


def test_throughput_is_invariant_to_compression():
    """makespan folds in the arrival spread, so dividing by it made a knob
    documented as not scaling throughput scale it ~9x."""
    fast = compressed(1e-6)
    slow = compressed(1e-4)
    slow.makespan_seconds = fast.makespan_seconds * 100
    assert slow.throughput_bytes_per_second == pytest.approx(fast.throughput_bytes_per_second)


def test_capacity_divisor_counts_every_item_offered_not_only_survivors():
    """items_per_aoi came from frame groups that happened to SUCCEED, so a
    truncated run collapsed the divisor and overstated capacity up to 4x."""
    from understory_perf.runner import capacity_aoi_count

    full = make_result(n_items=8, service_seconds=100.0, workers=4)
    for index, timing in enumerate(full.timings):
        timing["frame_group"] = index % 4

    truncated = make_result(n_items=8, service_seconds=100.0, workers=4, n_failed=6)
    for index, timing in enumerate(truncated.timings):
        # The two survivors only cover frame groups 0 and 1.
        timing["frame_group"] = index % 4 if timing["ok"] else (index % 4)
    assert capacity_aoi_count(truncated, 1.0) == pytest.approx(capacity_aoi_count(full, 1.0))


def test_capacity_uses_the_run_deadline_not_a_hardcoded_cycle():
    """A 30-day reprocessing deadline scored against a hardcoded 12-day cycle
    made capacity and utilization in the same report disagree by 2.5x."""
    from understory_perf.runner import capacity_aoi_count

    result = make_result(n_items=8, service_seconds=100.0, workers=4)
    for index, timing in enumerate(result.timings):
        timing["frame_group"] = index % 4
    result.model_deadline_seconds = 30 * SECONDS_PER_DAY
    thirty_day = capacity_aoi_count(result, 1.0)

    result.model_deadline_seconds = 12 * SECONDS_PER_DAY
    twelve_day = capacity_aoi_count(result, 1.0)
    assert thirty_day is not None and twelve_day is not None
    assert thirty_day / twelve_day == pytest.approx(30 / 12)


def test_rss_sampler_does_not_count_failed_reads():
    """samples is slo._memory's only "was this measured?" guard, so counting a
    failed read let a run with peak=0 report peak-memory PASS at 0.00 GB."""
    from understory_perf.runner import _RssSampler

    sampler = _RssSampler(interval=0.001)
    import psutil

    original = psutil.Process.memory_info

    def boom(self):
        raise psutil.AccessDenied(self.pid)

    psutil.Process.memory_info = boom
    try:
        sampler.start()
        time.sleep(0.05)
        sampler.stop()
    finally:
        psutil.Process.memory_info = original

    assert sampler.peak == 0
    assert sampler.samples == 0, "a read that produced nothing is not a sample"
    verdict = slo.evaluate(make_result(rss_samples=sampler.samples, peak_rss_bytes=0))
    assert status_of(verdict, "peak-memory") == "INSUFFICIENT_DATA"


def test_rescore_does_not_invent_a_sample_count():
    """from_report fabricating rss_samples=1 made an unmeasured run
    indistinguishable from a measured one once rescore wrote it back."""
    from understory_perf.runner import RunResult

    report = {
        "scenario": "x",
        "workload": {"name": "w", "compression": 1e-4, "notes": []},
        "run": {
            "config": {"workers": 4},
            "height_px": 10,
            "width_px": 10,
            "peak_total_rss_gb": 2.0,
            "makespan_seconds": 1.0,
            "deadline_days": 12.0,
            "n_failed": 0,
        },
        "timings": [],
    }
    assert RunResult.from_report(report).rss_samples == 0
