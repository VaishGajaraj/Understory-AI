# understory-perf

Load and latency harness for the Understory detection pipeline.

It answers one question with numbers rather than adjectives:

> **How many AOIs can this pipeline monitor on a given machine without falling
> permanently behind NISAR's 12-day repeat cycle — and where does it break?**

Nothing in the science packages imports this. It drives them from above, which
is why it sits at the top of the import-linter layer stack.

## Why utilization is the metric that matters

NISAR products arrive on a fixed 12-day cadence and never stop. If one cycle's
work takes longer than one cycle to process, the backlog grows every 12 days
and no amount of patience recovers it. So the ship / no-ship call is a
utilization ratio — offered work over capacity — not a latency percentile.
Latency describes how bad it feels; utilization decides whether it is
survivable.

Latency still has a hard budget, and it comes from the science rather than from
ops taste: `kill_criteria.LEAD_OVER_OPTICAL_MIN_DAYS` requires a median 21-day
detection lead over optical alert systems. Every hour an alert spends in a
queue is an hour subtracted from that lead. The harness budgets 5% of the
margin — about 25 hours — to processing.

Thresholds live in `slo.py`, stated before the run and evaluated mechanically,
in the same spirit as `understory_detect.kill_criteria`.

## Running it

```bash
uv run understory-load packages/understory-perf/scenarios/cycle-burst.yaml
make load-test          # the CI-sized scenario
make load-test-full     # every scenario, including the ones expected to fail
```

Exit status is 0 when every objective passes and 1 when any fails, so a
scenario can gate a deploy.

Re-judging a stored run costs nothing:

```bash
uv run understory-load --rescore reports/cycle-burst-9.json
```

Per-item timings are the expensive part of a load run, and every derived metric
is a pure function of them. Use this when an SLO threshold moves and old runs
need re-judging against it — or when a derived metric turns out to have been
computed wrongly, which has already happened once (see "compression" below).

## Compression: what it does and does not scale

A 12-day cycle cannot be replayed in wall clock, so scenarios compress the
*arrival spacing* by default (`compression: 1e-4` replays the pattern ~10,000x
faster). Service times, memory and throughput are measured against the real
detector on real-sized arrays and are never scaled.

That asymmetry is easy to get wrong, and the harness did get it wrong: dividing
real service seconds by a compressed deadline overstated utilization by
1/compression, reporting 2.11 for a workload actually using 0.02% of a cycle.
Two things follow, both now pinned by tests:

- **`utilization` is computed against the real deadline** and is invariant to
  compression. It is the capacity number and the ship / no-ship call.
- **`burst_utilization`** reports the compressed window the run actually
  experienced. It is a stress figure, not a capacity figure: it says how far
  past its sustainable arrival rate the pipeline was pushed and still finished.

Likewise, end-to-end latency measured under compressed arrivals is a stress
result. The `alert-latency-p95` objective uses service time, because at the real
cadence the queue is empty whenever utilization is below 1; the burst figure is
carried in the objective's note rather than mistaken for a prediction.

## Scenarios

| Scenario | Shape | What it tells you |
|---|---|---|
| `steady-cycle.yaml` | Arrivals spread across the cycle | Sustainable throughput — the load that never stops |
| `cycle-burst.yaml` | Same volume in 5% of the window | Burst tolerance, isolated from raw throughput |
| `reprocess-backlog.yaml` | Whole archive at t=0 | The Q4 2026 calibrated-reprocessing campaign |
| `fine-posting.yaml` | 20 m instead of 80 m coherence | 16x the pixels; the scientifically necessary case, and the one that breaks first |

Comparing `steady-cycle` against `cycle-burst` is the point of having both: the
volume is identical, so any difference is burst behaviour and not capacity.

## What is synthetic, and what that costs

Stacks are synthesized in memory at the real shape, dtype and size rather than
pulled from ASF. A single 24-pair stack over one frame at 20 m posting is
~46 GB of egress; nobody re-runs that per commit, and a load test nobody runs
is not a load test. The synthetic array exercises the identical memory and
compute path.

What it cannot tell you is anything about ASF itself — real download
throughput, Earthdata auth, S3 credential expiry, HDF5 decompression on real
granules. `tasks.ingest_task` measures that separately against granules on
disk, and those numbers must not be inferred from a synthetic run.

Arrival *spacing* is compressed (a 12-day cycle cannot be run in wall clock);
the compression factor is recorded in every report. Service times, memory and
throughput are measured and never scaled.

## Reading a report

Reports are machine-generated JSON, and capacity numbers quoted anywhere else
in the project should be traceable to one — same discipline as benchmark
tables. Each carries the git revision, the machine it ran on, the full run
config, per-item timings, and the SLO verdict.

The two numbers to read first:

- `capacity.aoi_at_slo_utilization` — how many AOIs this configuration
  supports with the SLO's headroom intact.
- `slo.objectives[].status` — `PASS`, `FAIL`, or `INSUFFICIENT_DATA`.

Measured results and the scaling analysis are written up in
[`docs/PERFORMANCE.md`](../../docs/PERFORMANCE.md).
