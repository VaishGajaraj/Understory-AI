"""Arrival models — what the pipeline is actually asked to absorb.

Three shapes matter, and they are genuinely different loads:

1. ``steady_cycle`` — the ordinary state. Every 12 days each monitored AOI gets
   a fresh pair on each of its frame groups. Products do not land as a batch:
   ASF forward-processes per datatake, so arrivals are spread across the cycle.
   This is the load the system must sustain forever, and the one where falling
   behind is fatal rather than inconvenient.

2. ``cycle_burst`` — the same volume, delivered badly. A datatake covering many
   AOIs completes at once, or a processing outage drains into a single window.
   Same work per cycle, far worse instantaneous rate. This is the spike test.

3. ``reprocess_backlog`` — the Q4 2026 validated reprocessing campaign, in which
   the entire archive is reissued and every benchmark must be recomputed on
   products that supersede what it was built on. It is a known, dated,
   whole-archive event, and it is the largest load this project will ever see.

Onboarding is a fourth shape (``aoi_backfill``): a new AOI needs its whole
history ingested before it produces a single alert, so its cost lands up front.

Arrival times are in seconds of *model* time. A 12-day cycle cannot be run in
wall clock, so scenarios compress it; the runner records the compression and
the report states it. Service times are never compressed — those are measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from understory_perf.nisar_scale import (
    FRAME_GROUPS_PER_AOI,
    REPEAT_CYCLE_DAYS,
    pairs_per_year,
)

SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True)
class WorkItem:
    """One unit of pipeline work: one frame group's stack, ready to detect."""

    aoi: str
    frame_group: int
    n_pairs: int
    # Deterministic seed so a scenario replays identically run to run.
    seed: int


@dataclass(frozen=True)
class Arrival:
    """A work item and the model-time offset at which it becomes available."""

    at_seconds: float
    item: WorkItem


@dataclass(frozen=True)
class Workload:
    """A named arrival sequence plus the budget it has to be finished inside."""

    name: str
    description: str
    arrivals: list[Arrival]
    # Wall-clock deadline for the whole sequence, in model seconds. Exceeding it
    # means the queue grows without bound cycle over cycle.
    deadline_seconds: float
    # Model seconds per real day, so the report can state what was compressed.
    seconds_per_model_day: float = SECONDS_PER_DAY
    notes: list[str] = field(default_factory=list)

    @property
    def n_items(self) -> int:
        return len(self.arrivals)

    @property
    def n_pairs(self) -> int:
        return sum(a.item.n_pairs for a in self.arrivals)

    @property
    def span_seconds(self) -> float:
        if not self.arrivals:
            return 0.0
        return max(a.at_seconds for a in self.arrivals)


def _spread(n: int, over_seconds: float) -> list[float]:
    """Evenly spaced offsets — deterministic, no RNG in arrival timing."""
    if n <= 1:
        return [0.0] * n
    return [i * over_seconds / (n - 1) for i in range(n)]


def steady_cycle(
    n_aoi: int,
    *,
    stack_depth: int = 24,
    frame_groups: int = FRAME_GROUPS_PER_AOI,
    compression: float = 1.0,
) -> Workload:
    """One repeat cycle of ordinary operations over ``n_aoi`` AOIs.

    ``compression`` scales model time: 1.0 means a real 12-day cycle, 0.001
    means the same arrival *pattern* replayed 1000x faster. Service times are
    unaffected — only the spacing between arrivals changes.
    """
    cycle_seconds = REPEAT_CYCLE_DAYS * SECONDS_PER_DAY * compression
    items = [
        WorkItem(aoi=f"aoi-{a:04d}", frame_group=g, n_pairs=stack_depth, seed=a * 31 + g)
        for a in range(n_aoi)
        for g in range(frame_groups)
    ]
    offsets = _spread(len(items), cycle_seconds)
    return Workload(
        name=f"steady-cycle-{n_aoi}aoi",
        description=(
            f"{n_aoi} AOIs x {frame_groups} frame groups, one new pair each per "
            f"{REPEAT_CYCLE_DAYS}-day cycle, arriving spread across the cycle"
        ),
        arrivals=[Arrival(t, item) for t, item in zip(offsets, items, strict=True)],
        deadline_seconds=cycle_seconds,
        seconds_per_model_day=SECONDS_PER_DAY * compression,
        notes=[
            "Deadline is one repeat cycle: a cycle's work must finish before the "
            "next cycle lands, or the backlog grows without bound.",
        ],
    )


def cycle_burst(
    n_aoi: int,
    *,
    stack_depth: int = 24,
    frame_groups: int = FRAME_GROUPS_PER_AOI,
    burst_fraction: float = 0.05,
    compression: float = 1.0,
) -> Workload:
    """A cycle's work delivered in ``burst_fraction`` of the cycle window.

    Same total volume as ``steady_cycle``, same deadline — but the instantaneous
    arrival rate is 1/burst_fraction higher. This is what a datatake completing
    over many AOIs at once, or a drained ASF outage, actually looks like.
    """
    base = steady_cycle(
        n_aoi, stack_depth=stack_depth, frame_groups=frame_groups, compression=compression
    )
    burst_seconds = base.deadline_seconds * burst_fraction
    offsets = _spread(base.n_items, burst_seconds)
    return Workload(
        name=f"cycle-burst-{n_aoi}aoi",
        description=(
            f"{n_aoi} AOIs x {frame_groups} frame groups all landing within "
            f"{burst_fraction:.0%} of one {REPEAT_CYCLE_DAYS}-day cycle"
        ),
        arrivals=[Arrival(t, a.item) for t, a in zip(offsets, base.arrivals, strict=True)],
        deadline_seconds=base.deadline_seconds,
        seconds_per_model_day=base.seconds_per_model_day,
        notes=[
            f"Same volume as steady-cycle-{n_aoi}aoi; only the arrival rate differs. "
            "Compare the two runs to separate a throughput problem from a burst problem.",
        ],
    )


def reprocess_backlog(
    n_aoi: int,
    *,
    history_years: float = 1.0,
    frame_groups: int = FRAME_GROUPS_PER_AOI,
    deadline_days: float = 30.0,
    compression: float = 1.0,
) -> Workload:
    """The Q4 2026 validated-reprocessing campaign.

    Every product is reissued, so every stack is rebuilt and every benchmark
    rerun from scratch. Arrives all at once and has to clear inside
    ``deadline_days``, during which the steady cycle keeps running underneath.
    """
    depth = int(pairs_per_year() * history_years)
    items = [
        WorkItem(aoi=f"aoi-{a:04d}", frame_group=g, n_pairs=depth, seed=a * 31 + g)
        for a in range(n_aoi)
        for g in range(frame_groups)
    ]
    return Workload(
        name=f"reprocess-backlog-{n_aoi}aoi",
        description=(
            f"Full rebuild of {n_aoi} AOIs x {frame_groups} frame groups x {depth} pairs "
            f"({history_years:g} yr history) — the calibrated-stream reprocessing gate"
        ),
        arrivals=[Arrival(0.0, item) for item in items],
        deadline_seconds=deadline_days * SECONDS_PER_DAY * compression,
        seconds_per_model_day=SECONDS_PER_DAY * compression,
        notes=[
            "Everything arrives at t=0: reprocessing supersedes prior products wholesale.",
            "The steady cycle continues during this window and is not modeled here — "
            "subtract its utilization from available capacity before reading the verdict.",
        ],
    )


def aoi_backfill(
    n_aoi: int,
    *,
    history_years: float = 1.0,
    frame_groups: int = FRAME_GROUPS_PER_AOI,
    deadline_days: float = 12.0,
    compression: float = 1.0,
) -> Workload:
    """Onboarding: new AOIs need full history before they emit a first alert."""
    depth = int(pairs_per_year() * history_years)
    items = [
        WorkItem(aoi=f"new-aoi-{a:04d}", frame_group=g, n_pairs=depth, seed=a * 17 + g)
        for a in range(n_aoi)
        for g in range(frame_groups)
    ]
    return Workload(
        name=f"aoi-backfill-{n_aoi}aoi",
        description=(
            f"Onboard {n_aoi} new AOIs, each needing {depth} pairs of history on "
            f"{frame_groups} frame groups before its first alert"
        ),
        arrivals=[Arrival(0.0, item) for item in items],
        deadline_seconds=deadline_days * SECONDS_PER_DAY * compression,
        seconds_per_model_day=SECONDS_PER_DAY * compression,
        notes=["A backfilled AOI produces no alerts until its stack reaches min_history_pairs."],
    )


BUILDERS = {
    "steady-cycle": steady_cycle,
    "cycle-burst": cycle_burst,
    "reprocess-backlog": reprocess_backlog,
    "aoi-backfill": aoi_backfill,
}


def build(shape: str, n_aoi: int, **kwargs) -> Workload:
    if shape not in BUILDERS:
        raise KeyError(f"unknown workload shape '{shape}' (known: {sorted(BUILDERS)})")
    return BUILDERS[shape](n_aoi, **kwargs)
