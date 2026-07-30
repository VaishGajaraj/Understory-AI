"""Execute a workload against the real pipeline and measure what happens.

The measurement that decides ship / no-ship is **utilization**: offered work
per cycle divided by capacity per cycle. Below 1.0 the queue drains and latency
is bounded; at or above 1.0 the backlog grows every cycle and the system is
already broken, however healthy a short run looks. Latency percentiles describe
how bad it feels; utilization decides whether it is survivable.

Arrival spacing is model time and may be compressed (a 12-day cycle cannot be
run in wall clock). Service times, memory and throughput are never compressed —
they are measured against the real detector on real-sized arrays.
"""

from __future__ import annotations

import contextlib
import math
import os
import statistics
import sys
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass, field

from understory_core.tiling import DEFAULT_TILE_BUDGET_BYTES

from understory_perf.tasks import StageTiming, detect_task, geometry_for
from understory_perf.workload import Workload

# How often the parent samples total resident memory across itself and workers.
RSS_SAMPLE_INTERVAL_S = 0.05


@dataclass(frozen=True)
class RunConfig:
    """Everything that changes a measurement, in one object the report embeds."""

    posting: str = "coarse"
    aoi_side_km: float = 100.0
    workers: int = field(default_factory=lambda: max(1, (os.cpu_count() or 2) - 1))
    max_working_bytes: int = DEFAULT_TILE_BUDGET_BYTES
    # Cap so a scenario that has fallen off a cliff cannot run forever.
    timeout_seconds: float = 1800.0
    # Per-item progress to stderr. On by default: a scenario can run for tens of
    # minutes, and a silent one is indistinguishable from a hung one.
    progress: bool = True

    @property
    def geometry(self) -> tuple[int, int]:
        return geometry_for(self.posting, self.aoi_side_km)


@dataclass
class RunResult:
    """Everything measured in one run. Serialized verbatim into the report."""

    workload: str
    description: str
    config: dict
    height_px: int
    width_px: int
    timings: list[dict]
    peak_total_rss_bytes: int
    rss_samples: int
    makespan_seconds: float
    model_deadline_seconds: float
    seconds_per_model_day: float
    n_failed: int
    notes: list[str] = field(default_factory=list)

    # --- derived metrics ---

    @property
    def ok_timings(self) -> list[dict]:
        return [t for t in self.timings if t["ok"]]

    @property
    def latencies(self) -> list[float]:
        """Available-to-complete, in seconds: what an alert consumer waits."""
        return sorted(
            (t["service_start"] - t["available_at"]) + t["service_seconds"] for t in self.ok_timings
        )

    @property
    def queue_waits(self) -> list[float]:
        return sorted(t["service_start"] - t["available_at"] for t in self.ok_timings)

    @property
    def service_times(self) -> list[float]:
        return sorted(t["service_seconds"] for t in self.ok_timings)

    @property
    def total_service_seconds(self) -> float:
        return sum(t["service_seconds"] for t in self.ok_timings)

    @property
    def total_input_bytes(self) -> int:
        return sum(t["input_bytes"] for t in self.ok_timings)

    @property
    def throughput_bytes_per_second(self) -> float:
        """Bytes per second of worker time, not of wall clock.

        Dividing by makespan would fold in the arrival spread, making the number
        a function of the compression knob -- which the harness documents as not
        scaling throughput. Summed service time over summed bytes is the rate the
        pipeline actually sustains, and is compression-invariant.
        """
        service = self.total_service_seconds
        if service <= 0:
            return 0.0
        return self.total_input_bytes / service * max(1, int(self.config["workers"]))

    @property
    def compression(self) -> float:
        """Model seconds per real second. 1.0 means the run was not compressed."""
        return self.seconds_per_model_day / 86_400.0

    @property
    def real_deadline_seconds(self) -> float:
        """The deadline in real seconds, undoing any arrival-time compression.

        Service times are measured in real seconds and are never compressed, so
        anything that divides work by the deadline has to use this rather than
        the compressed model deadline. Comparing real work against a compressed
        window overstates utilization by 1/compression, which for the default
        1e-4 is a factor of ten thousand.
        """
        return self.model_deadline_seconds / self.compression if self.compression else 0.0

    @property
    def utilization(self) -> float | None:
        """Offered work over capacity, per real repeat cycle.

        Summed real service time against the parallel worker-seconds available
        in one real deadline window. >= 1.0 means the backlog grows every cycle
        and the system is already broken. This is the ship / no-ship number.
        """
        capacity = self.real_deadline_seconds * self.config["workers"]
        if capacity <= 0:
            return None
        return self.total_service_seconds / capacity

    @property
    def burst_utilization(self) -> float | None:
        """Utilization against the *compressed* window the run actually saw.

        Not a capacity figure — the arrival rate is artificial. It says how far
        past its sustainable rate the pipeline was pushed and still completed,
        which is exactly what a spike test is for.
        """
        capacity = self.model_deadline_seconds * self.config["workers"]
        if capacity <= 0:
            return None
        return self.total_service_seconds / capacity

    @property
    def projected_completion_seconds(self) -> float:
        """Real seconds to clear the workload at the measured rate."""
        workers = max(1, int(self.config["workers"]))
        return self.total_service_seconds / workers

    @classmethod
    def from_report(cls, report: dict) -> RunResult:
        """Rebuild a RunResult from a report JSON.

        Every derived metric is a pure function of the stored fields, so a run
        can be re-scored without re-running it. That matters twice: when an SLO
        threshold changes and old runs need re-judging against it, and when a
        bug is found in a derived metric — the expensive part is the per-item
        timings, and those stay valid.
        """
        run, workload = report["run"], report["workload"]
        deadline_days = run["deadline_days"]
        compression = workload.get("compression", 1.0)
        seconds_per_model_day = 86_400.0 * compression
        return cls(
            workload=workload["name"],
            description=workload.get("description", ""),
            config=run["config"],
            height_px=run["height_px"],
            width_px=run["width_px"],
            timings=report["timings"],
            peak_total_rss_bytes=int(round(run["peak_total_rss_gb"] * 1e9)),
            # 0 when the report predates the field. Inventing a count here would
            # be written back by cli.rescore and become indistinguishable from a
            # genuinely sampled run, and slo._memory reads it as "was this
            # measured at all?" -- so an unknown must stay unknown.
            rss_samples=run.get("rss_samples", 0),
            makespan_seconds=run["makespan_seconds"],
            model_deadline_seconds=deadline_days * seconds_per_model_day,
            seconds_per_model_day=seconds_per_model_day,
            n_failed=run["n_failed"],
            notes=workload.get("notes", []),
        )

    def percentile(self, values: list[float], fraction: float) -> float | None:
        """Linear-interpolation percentile, matching numpy's default.

        The obvious nearest-rank form -- round(f * (n-1)) -- returns the maximum
        for p99 at every n <= 51 and for p95 at every n <= 11, which is every
        scenario size this project actually runs. That silently turned the
        alert-latency SLO into a gate on the worst single item.

        A percentile over 24 items is still a weak statistic; ``n_items`` is in
        the report so a reader can judge it.
        """
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        position = fraction * (len(values) - 1)
        lower = int(math.floor(position))
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    def summary(self) -> dict:
        latencies = self.latencies
        return {
            "n_items": len(self.timings),
            "n_failed": self.n_failed,
            "rss_samples": self.rss_samples,
            "makespan_seconds": round(self.makespan_seconds, 3),
            "service_seconds_p50": _r(self.percentile(self.service_times, 0.50)),
            "service_seconds_p95": _r(self.percentile(self.service_times, 0.95)),
            "service_seconds_max": _r(max(self.service_times, default=None)),
            "queue_wait_p95": _r(self.percentile(self.queue_waits, 0.95)),
            "latency_p50": _r(self.percentile(latencies, 0.50)),
            "latency_p95": _r(self.percentile(latencies, 0.95)),
            "latency_p99": _r(self.percentile(latencies, 0.99)),
            "latency_max": _r(max(latencies, default=None)),
            "throughput_mb_per_s": _r(self.throughput_bytes_per_second / 1e6),
            "total_input_gb": _r(self.total_input_bytes / 1e9),
            "peak_total_rss_gb": _r(self.peak_total_rss_bytes / 1e9),
            "peak_rss_per_worker_gb": _r(
                max((t["peak_rss_bytes"] for t in self.timings), default=0) / 1e9
            ),
            "utilization": _r(self.utilization, 6),
            "burst_utilization": _r(self.burst_utilization, 4),
            "compression": _r(self.compression, 8),
            "projected_completion_days": _r(self.projected_completion_seconds / 86_400.0, 6),
            "deadline_days": _r(self.real_deadline_seconds / 86_400.0, 3),
        }


def _r(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


class _RssSampler(threading.Thread):
    """Sample total resident memory of this process tree until stopped.

    Total across the tree, not per process: the question a load test answers is
    whether the run fits on the box, and N workers each inside their own budget
    can still exhaust it together.
    """

    def __init__(self, interval: float = RSS_SAMPLE_INTERVAL_S):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0
        self.samples = 0
        # Not `self._stop`: threading.Thread has a private _stop() that the
        # interpreter calls during shutdown, and shadowing it with an Event
        # makes every run die with "'Event' object is not callable" *after*
        # finishing its work.
        self._stop_event = threading.Event()

    def run(self) -> None:
        try:
            import psutil
        except ImportError:
            return
        me = psutil.Process()
        while not self._stop_event.is_set():
            try:
                total = me.memory_info().rss + sum(
                    child.memory_info().rss for child in me.children(recursive=True)
                )
            except Exception:  # noqa: BLE001 - a vanished child is normal
                # Do NOT count a failed read as a sample: slo._memory uses
                # samples == 0 as its only "was this measured?" guard, and a run
                # where every read raised would otherwise report PASS at 0.00 GB.
                self._stop_event.wait(self.interval)
                continue
            self.peak = max(self.peak, total)
            self.samples += 1
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=2.0)


def _log_progress(timing: StageTiming, done: int, total: int) -> None:
    status = "ok" if timing.ok else f"FAILED {timing.error}"
    print(
        f"  [{done:>4}/{total}] {timing.aoi}/{timing.frame_group} "
        f"{timing.service_seconds:7.1f}s {timing.peak_rss_bytes / 1e9:5.2f}GB {status}",
        file=sys.stderr,
        flush=True,
    )


def _unfinished(workload: Workload, count: int, config: RunConfig) -> list[StageTiming]:
    """Placeholder timings for items that never completed inside the timeout.

    Recorded as explicit failures so the failure-rate objective sees them. An
    item silently missing from the results would read as a smaller, faster
    workload than the one actually offered.
    """
    height_px, width_px = config.geometry
    return [
        StageTiming(
            aoi="(timed out)",
            frame_group=-1,
            stage="detect",
            n_pairs=0,
            input_bytes=0,
            available_at=0.0,
            service_start=0.0,
            service_seconds=0.0,
            peak_rss_bytes=0,
            ok=False,
            error=f"timed out after {config.timeout_seconds:.0f}s",
        )
        for _ in range(count)
    ]


def run(workload: Workload, config: RunConfig | None = None) -> RunResult:
    """Run a workload through the detector and return everything measured."""
    config = config or RunConfig()
    height_px, width_px = config.geometry

    sampler = _RssSampler()
    sampler.start()
    timings: list[StageTiming] = []
    started = time.perf_counter()

    timed_out = 0
    pool = ProcessPoolExecutor(max_workers=config.workers)
    try:
        futures: list[Future] = []
        for arrival in sorted(workload.arrivals, key=lambda a: a.at_seconds):
            # Hold submission until the item's model arrival time, so a burst
            # really is a burst and the queue really does build.
            delay = arrival.at_seconds - (time.perf_counter() - started)
            if delay > 0:
                time.sleep(delay)
            futures.append(
                pool.submit(
                    detect_task,
                    arrival.item,
                    height_px,
                    width_px,
                    config.max_working_bytes,
                    time.time(),
                )
            )
        try:
            for future in as_completed(futures, timeout=config.timeout_seconds):
                timing = future.result()
                timings.append(timing)
                if config.progress:
                    _log_progress(timing, len(timings), len(futures))
        except FuturesTimeout:
            # A scenario overrunning its timeout is the loudest possible result,
            # so keep what completed and report the rest as failed rather than
            # raising away the whole measurement.
            #
            # cancel() only stops futures that have not started, so items already
            # running would otherwise keep going and the makespan would be
            # measured after they finished -- a timeout that did not bound the
            # run. Harvest anything that finished in the meantime, then kill the
            # pool without waiting.
            for future in futures:
                future.cancel()
            for future in futures:
                if future.done() and not future.cancelled():
                    # A worker that died taking its result with it is itself a
                    # result; count it among the timed-out rather than raising.
                    with contextlib.suppress(Exception):
                        timings.append(future.result(timeout=0))
            timed_out = len(futures) - len(timings)
    finally:
        makespan = time.perf_counter() - started
        # cancel_futures + no wait: the timeout must bound wall clock.
        pool.shutdown(wait=timed_out == 0, cancel_futures=True)
        sampler.stop()

    timings.extend(_unfinished(workload, timed_out, config))

    return RunResult(
        workload=workload.name,
        description=workload.description,
        config={
            "posting": config.posting,
            "posting_m": {"fine": 20.0, "coarse": 80.0}[config.posting],
            "aoi_side_km": config.aoi_side_km,
            "workers": config.workers,
            "max_working_bytes": config.max_working_bytes,
        },
        height_px=height_px,
        width_px=width_px,
        timings=[asdict(t) for t in timings],
        peak_total_rss_bytes=sampler.peak,
        rss_samples=sampler.samples,
        makespan_seconds=makespan,
        model_deadline_seconds=workload.deadline_seconds,
        seconds_per_model_day=workload.seconds_per_model_day,
        n_failed=sum(1 for t in timings if not t.ok),
        notes=list(workload.notes),
    )


def capacity_aoi_count(result: RunResult, target_utilization: float = 1.0) -> float | None:
    """How many AOIs this configuration could carry at a given utilization.

    Scales the measured per-item service time up against the run's own deadline.
    The answer the writeup needs is "how many AOIs can we monitor", and that is
    this number, not a latency percentile.

    Two things this deliberately does NOT do, both of which it used to:

    - Derive items-per-AOI from the frame groups that happened to *succeed*.
      That is a property of which items finished, so a truncated or partly
      failed run collapsed the divisor and overstated capacity by up to 4x.
      It now counts distinct frame groups across every item offered.
    - Hardcode a 12-day cycle. Workloads have different deadlines (reprocessing
      is 30 days), and using 12 for all of them made capacity disagree with the
      utilization computed from the same run by deadline_days/12.
    """
    ok = result.ok_timings
    if not ok:
        return None
    mean_service = statistics.fmean(t["service_seconds"] for t in ok)
    if mean_service <= 0:
        return None
    # Every item offered, not only those that completed.
    items_per_aoi = len({t["frame_group"] for t in result.timings if t["frame_group"] >= 0}) or 1
    capacity_seconds = result.real_deadline_seconds * result.config["workers"] * target_utilization
    return capacity_seconds / (mean_service * items_per_aoi)
