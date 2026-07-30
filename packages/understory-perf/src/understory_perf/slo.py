"""Service-level objectives as code — the ship / no-ship gate.

Same discipline as ``understory_detect.kill_criteria``: the thresholds are
stated before the run, evaluated mechanically, and embedded in every report. A
capacity claim assembled by hand after seeing the numbers is not a claim.

The thresholds are not arbitrary ops hygiene. Two of them fall out of the
project's own science gates:

- **Utilization.** A cycle's work must clear inside a repeat cycle. At or above
  1.0 the backlog grows every 12 days and no amount of patience recovers it.
  0.7 is the ship line, leaving headroom for the reprocessing campaigns and
  outage drains that are known to be coming.

- **Alert latency.** ``kill_criteria.LEAD_OVER_OPTICAL_MIN_DAYS`` requires a
  median 21-day lead over optical alerts. Pipeline latency is subtracted
  directly from that lead: an alert sitting in a queue is an alert not
  delivered. We budget at most 5% of the margin — about 25 hours — to
  processing, so the science claim survives the engineering.

- **Memory.** Peak resident memory must fit the target machine with room to
  spare. Exceeding it does not degrade, it OOM-kills mid-cycle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from understory_detect.kill_criteria import LEAD_OVER_OPTICAL_MIN_DAYS

Status = Literal["PASS", "FAIL", "INSUFFICIENT_DATA"]

# A cycle's work must clear well inside a cycle.
MAX_UTILIZATION = 0.70

# Share of the lead-over-optical margin we are willing to spend on processing.
LATENCY_BUDGET_FRACTION = 0.05
MAX_ALERT_LATENCY_HOURS = LEAD_OVER_OPTICAL_MIN_DAYS * 24 * LATENCY_BUDGET_FRACTION

# Target deployment: a single commodity 16 GB worker node. Chosen because the
# project's cost discipline is "tens of dollars per benchmark run, not
# thousands" — if the pipeline needs a 256 GB machine, that discipline is gone.
TARGET_NODE_MEMORY_GB = 16.0
MEMORY_HEADROOM_FRACTION = 0.75

# Any task failure under load is a fail: these are batch jobs with no retry
# semantics yet, so a dropped frame group is a silently missing alert.
MAX_FAILURE_RATE = 0.0


class Objective(BaseModel):
    name: str
    threshold: str
    observed: str
    status: Status
    note: str = ""


class SloVerdict(BaseModel):
    objectives: list[Objective]
    scenario: str
    synthetic_workload: bool = True

    @property
    def shippable(self) -> bool:
        return all(o.status != "FAIL" for o in self.objectives)


def evaluate(result, *, scenario: str | None = None) -> SloVerdict:
    """Evaluate a ``RunResult`` against the objectives above."""
    return SloVerdict(
        objectives=[
            _utilization(result),
            _latency(result),
            _memory(result),
            _failures(result),
        ],
        scenario=scenario or result.workload,
    )


def _utilization(result) -> Objective:
    utilization = result.utilization
    # A run with nothing in it has zero utilization, which would read as a
    # comfortable pass. Absence of work is absence of evidence.
    if utilization is None or not result.ok_timings:
        return Objective(
            name="cycle-utilization",
            threshold=f"<= {MAX_UTILIZATION:.2f}",
            observed=(
                "no deadline defined for this workload"
                if utilization is None
                else "no items completed successfully"
            ),
            status="INSUFFICIENT_DATA",
        )
    projected_hours = result.projected_completion_seconds / 3600.0
    deadline_days = result.real_deadline_seconds / 86_400.0
    note = f"{projected_hours:.2f} h of work against a {deadline_days:.1f} d deadline"
    if utilization >= 1.0:
        note += " — backlog grows every cycle"
    if result.compression < 1.0:
        note += (
            f"; the run itself sustained {result.burst_utilization:.2f} against a "
            f"{1 / result.compression:.0f}x compressed arrival window"
        )
    return Objective(
        name="cycle-utilization",
        threshold=f"<= {MAX_UTILIZATION:.2f}",
        # Healthy utilizations here are small enough that fixed decimals round
        # them to 0.000 and hide the headroom entirely.
        observed=f"{utilization:.3g}",
        status="PASS" if utilization <= MAX_UTILIZATION else "FAIL",
        note=note,
    )


def _latency(result) -> Objective:
    """Alert latency an operator would actually see, at the real arrival rate.

    A compressed run cannot measure this directly: its queue is fed thousands of
    times faster than reality, so its end-to-end latency is a stress figure, not
    a prediction. Scaling that figure back by 1/compression is worse than
    useless — it multiplies a real, already-elapsed measurement by ten thousand.

    At the real cadence the queue is empty whenever utilization is below 1, so
    latency is the service time. When utilization exceeds 1 there is no steady
    state and latency is unbounded, which the utilization objective already
    fails on; this one reports the service floor and says so.
    """
    p95_service = result.percentile(result.service_times, 0.95)
    if p95_service is None:
        return Objective(
            name="alert-latency-p95",
            threshold=f"<= {MAX_ALERT_LATENCY_HOURS:.0f} h",
            observed="no successful items",
            status="INSUFFICIENT_DATA",
        )
    hours = p95_service / 3600.0
    utilization = result.utilization
    note = (
        f"{LATENCY_BUDGET_FRACTION:.0%} of the {LEAD_OVER_OPTICAL_MIN_DAYS:g}-day "
        "lead-over-optical kill criterion"
    )
    burst_p95 = result.percentile(result.latencies, 0.95)
    if burst_p95 is not None and result.compression < 1.0:
        note += (
            f"; under a {1 / result.compression:.0f}x compressed arrival rate the measured "
            f"end-to-end p95 was {burst_p95 / 60:.1f} min"
        )
    if utilization is not None and utilization >= 1.0:
        note += "; queue is unstable at this utilization, so this is a floor, not a bound"
    return Objective(
        name="alert-latency-p95",
        threshold=f"<= {MAX_ALERT_LATENCY_HOURS:.0f} h",
        observed=f"{hours:.3f} h",
        status="PASS" if hours <= MAX_ALERT_LATENCY_HOURS else "FAIL",
        note=note,
    )


def _memory(result) -> Objective:
    budget_gb = TARGET_NODE_MEMORY_GB * MEMORY_HEADROOM_FRACTION
    peak_gb = result.peak_total_rss_bytes / 1e9
    if result.rss_samples == 0 or not result.ok_timings:
        return Objective(
            name="peak-memory",
            threshold=f"<= {budget_gb:.1f} GB",
            observed=(
                "not sampled (install psutil to measure)"
                if result.rss_samples == 0
                # An idle process staying under budget says nothing about
                # whether the workload would have.
                else "no items completed successfully"
            ),
            status="INSUFFICIENT_DATA",
        )
    return Objective(
        name="peak-memory",
        threshold=f"<= {budget_gb:.1f} GB",
        observed=f"{peak_gb:.2f} GB",
        status="PASS" if peak_gb <= budget_gb else "FAIL",
        note=(
            f"{result.config['workers']} workers on a {TARGET_NODE_MEMORY_GB:.0f} GB node "
            f"at {MEMORY_HEADROOM_FRACTION:.0%} headroom"
        ),
    )


def _failures(result) -> Objective:
    total = len(result.timings)
    if total == 0:
        return Objective(
            name="failure-rate",
            threshold=f"<= {MAX_FAILURE_RATE:.0%}",
            observed="no items ran",
            status="INSUFFICIENT_DATA",
        )
    rate = result.n_failed / total
    errors = sorted({t["error"] for t in result.timings if not t["ok"]})
    return Objective(
        name="failure-rate",
        threshold=f"<= {MAX_FAILURE_RATE:.0%}",
        observed=f"{rate:.1%} ({result.n_failed}/{total})",
        status="PASS" if rate <= MAX_FAILURE_RATE else "FAIL",
        note="; ".join(errors[:3]),
    )


def format_table(verdict: SloVerdict) -> str:
    lines = [f"service-level objectives ({verdict.scenario}):"]
    for objective in verdict.objectives:
        note = f"  ({objective.note})" if objective.note else ""
        lines.append(
            f"  [{objective.status:^17s}] {objective.name}: {objective.observed} "
            f"vs {objective.threshold}{note}"
        )
    lines.append(f"  verdict: {'SHIP' if verdict.shippable else 'DO NOT SHIP'}")
    return "\n".join(lines)
