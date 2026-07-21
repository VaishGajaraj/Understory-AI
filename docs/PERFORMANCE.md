# Performance and capacity

**A statement of confidence, not a report.** What the pipeline reliably handles
as it stands, where it breaks, and what it would take to go further.

Every number here was produced by `understory-perf` on the hardware named below
and is reproducible with `make load-test-full`. Capacity claims that cannot be
traced to a report file under `reports/` do not belong in this document — the
same discipline the benchmark tables are held to.

## Verdict

**Ship, for the 80 m detection path, at any AOI count this project will
plausibly reach.** Every service-level objective passed on every scenario, with
zero failed items across 56. A 12-day cycle's compute for a 100 km AOI is ~38
seconds per frame group against a cycle window of twelve days — a utilization of
0.0002. Delivering that cycle's arrivals 20× faster changed nothing measurable
except queue latency.

**Two caveats, and the second is the one that matters.**

The first is bounded and understood: at 20 m posting, memory rather than CPU
sets the worker count, and a 16 GB node fits two concurrent items.

The second is that **this document measures compute, not ingest.** The pipeline
downloads whole 1.9 GB granules to read one layer, and that path has no load
coverage at all. Given how much compute headroom the measurements show, ingest
is almost certainly the real constraint — so the honest statement of confidence
is: *the detection path is not what will limit this system, and we have not yet
measured the thing that will.*

Getting to this verdict required fixing defects that would each have been fatal
at scale: two in the pipeline, five in the harness that measures it, and several
more in the stack builder found by an adversarial pre-push review. They are
documented below, because the measurements are the justification for code that
otherwise looks like premature optimization — and because the harness's own bugs
are the strongest argument for not trusting a number just because a tool printed
it.

## The question this answers

NISAR products arrive on a fixed 12-day cadence and never stop. That makes
capacity a stability question rather than a speed question:

> **Can a cycle's work be processed before the next cycle lands?**

If not, the backlog grows every 12 days and no amount of patience recovers it.
So the ship / no-ship call is a utilization ratio — offered work over capacity —
not a latency percentile. Latency describes how bad it feels; utilization
decides whether it is survivable.

Latency still has a hard budget, and it comes from the science. The
`lead-over-optical` kill criterion requires a median 21-day detection lead over
optical alert systems. Every hour an alert spends in a queue is an hour
subtracted from that lead. We budget 5% of the margin — about 25 hours — to
processing, so an engineering regression cannot quietly consume a scientific
claim. That coupling is the reason the SLOs live in code
(`understory_perf/slo.py`) next to the kill criteria rather than in a runbook.

## Test hardware

| | |
|---|---|
| Machine | Apple Silicon, 10 cores (performance + efficiency), 17.2 GB RAM |
| Python | 3.12.13 |
| Workers | 4, pinned in every scenario that this document quotes |

A single commodity node, deliberately. The project's cost discipline is "tens of
dollars per benchmark run, not thousands"; if the pipeline needs a 256 GB
machine, that discipline is gone.

**Per-core throughput is not uniform on this machine.** An item that takes ~31 s
alone on a performance core takes ~38 s under 4-way concurrency, and degrades
much further at 9-way as the scheduler falls back to efficiency cores and memory
bandwidth saturates. That is why the scenarios pin 4 rather than `cpu_count − 1`:
utilization scales linearly in worker count, so an unpinned default would make
every row here irreproducible on a machine with a different core count. Anyone
extrapolating from a single-item timing on a homogeneous cloud instance will get
a different — probably better — number.

## What was wrong, and what fixed it

Building the harness turned up two defects in the pipeline; an adversarial
pre-push review then turned up five more in the harness itself and several in
the stack builder. All are fixed and pinned by regression tests, each of which
reproduces the original failure.

### 1. Baseline memory scaled with AOI size, not with a budget

`expected_coherence` materializes a `(time, y, x, window)` array via
`rolling(...).construct()`. Peak memory was therefore proportional to AOI area,
and the constant was large. Measured on the original code:

| Stack | Input | Wall time | Peak RSS |
|---|---:|---:|---:|
| 512² × 24 | 25 MB | 3.9 s | 1.65 GB |
| 1024² × 24 | 101 MB | 19.2 s | 3.40 GB |
| 2048² × 24 | 403 MB | 174.0 s | 6.85 GB |

That is roughly **17× the input in resident memory**, and time growing faster
than linearly as the machine came under pressure. Extrapolating to a real NISAR
frame: a 24-pair stack over a 100 km AOI at the 20 m coherence posting is 2.4 GB,
which would have needed ~38 GB of working memory. A full frame at 20 m is
15.5 GB of stack. Neither fits anywhere reasonable.

**Fix:** evaluate the baseline in spatial tiles
(`understory_core/tiling.py`). The rolling baseline is per-pixel along time, so
tiling is *exact* rather than approximate — `test_baseline_tiling.py` asserts
tiled and untiled results are bit-identical, including on non-square grids and
degenerate shapes. Connected-component labeling is not tileable this way (a skid
trail crossing a tile edge would become two events), so it still runs on the
assembled boolean mask, which is 4× smaller than the float32 stack it came from.

Peak memory now follows `BaselineConfig.max_working_bytes` instead of AOI area.

### 2. The persistence filter did boolean logic in float64

`persistence_filter` used `rolling(time=n).sum()` on a boolean mask. `rolling`
upcasts to float64 and materializes a window array — 1.5 GB of floating-point
arithmetic on a 100 km AOI to answer a question about booleans. A per-stage
memory profile made it obvious:

| Stage | Peak RSS after |
|---|---:|
| stack built (150 MB) | 0.58 GB |
| `anomaly_deficit` | 3.36 GB |
| candidates | 3.36 GB |
| **`persistence_filter`** | **4.86 GB** |
| cluster | 4.86 GB |
| `extract_events` | 4.87 GB |

**Fix:** a chain of shifted boolean ANDs, holding at most two boolean arrays.
Identical results — the toy benchmark returns precision 1.00, recall 1.00,
latency 22 d, verdict unchanged.

### The memory model had to be measured, not derived

Reading the source suggests peak memory is `2 × window_pairs × slab_bytes`: the
constructed window stack plus the deviation from its median. Measurement says
otherwise — `nanmedian` sorts a copy, the validity count is another
window-sized array, and freed blocks stay in the allocator's arenas rather than
returning to the OS. Across five slab shapes the measured factor was 8.25, 8.24,
8.66, 9.16 and 9.65.

`BASELINE_MEMORY_FACTOR` is set to **10**, because the number that matters is
what the OOM killer sees and being wrong in this direction is cheap. It is
calibrated by `scripts/measure_baseline_memory.py`, guarded by a unit test, and
re-checked in CI — under-budgeting does not degrade gracefully, it OOM-kills a
run mid-cycle.

This is the part worth generalizing: **the tile sizer's constant is the single
number that decides how large an AOI fits on a machine, and reasoning about it
from the source was wrong by 5×.**

### 3. The harness's own metrics were wrong in four ways

Worth recording in detail, because a harness that reports a wrong number is
worse than no harness — it gets believed. All four were caught by an adversarial
review that required every finding to be reproduced by running code, and all
four are now pinned by regression tests.

**Utilization was 10,000× too high.** The headline one, below.

**`p99` was literally the maximum.** The percentile used nearest-rank —
`round(f × (n−1))` — which returns the last element for p99 at every n ≤ 51 and
for p95 at every n ≤ 11. Every scenario this project runs is in that range, so
every reported `latency_p99` was `latency_max`, and the `alert-latency-p95` gate
was gating on the single worst item. Now linear interpolation, matching numpy.

**Capacity was overstated by up to 4×, and disagreed with utilization by 2.5×.**
Two independent bugs in one function. It derived items-per-AOI from the frame
groups that happened to *succeed*, so a truncated run collapsed the divisor; and
it hardcoded a 12-day cycle, so the 30-day reprocessing scenario's capacity
contradicted the utilization computed from the same run. That is why
`reprocess-backlog-2` now reads 39,279 AOIs rather than the 15,712 first
recorded here.

**Throughput moved with the compression knob.** It divided real bytes by wall
clock, and wall clock includes the compressed arrival spread — two identical
runs differing only in compression reported 1.66 and 0.19 MB/s. Now measured
against worker time.

A fifth, in the same spirit: the memory sampler counted reads that had *failed*,
so a run where every read raised would report `peak-memory PASS at 0.00 GB`
instead of INSUFFICIENT_DATA — the guard existed and was defeated by its own
counter.

**The general lesson: a load harness needs its own regression tests as much as
the code it measures.** Four of these five were invisible to a reader and only
fell out of running the code against hand-computed expectations.

### The utilization bug in detail

A 12-day cycle cannot be replayed in wall clock, so scenarios compress the
*arrival spacing* — the default replays the pattern 10,000× faster. Service
times are measured against the real detector and are not compressed. The
utilization calculation divided real service seconds by the *compressed*
deadline, overstating it by exactly 1/compression.

The first scenario duly reported utilization 2.11 and **DO NOT SHIP** for a
workload actually using 0.02% of a cycle. The latency objective had the
mirror-image error, multiplying an already-elapsed 37-second measurement by
10,000 to get 598 hours.

What made it catchable was that the two numbers disagreed with each other:
utilization said the system was 2× oversubscribed while the capacity
extrapolation — which correctly used real cycle seconds — said 19,000 AOIs.
Both could not be true.

Fixed by computing utilization against the real deadline and reporting
`burst_utilization` separately for the compressed window the run actually
experienced. Since every derived metric is a pure function of the stored
per-item timings, `understory-load --rescore` re-judges completed runs without
re-running them — which is how the numbers below were corrected without paying
for another hour of measurement.

### Result

Same 100 km AOI, 24 pairs, 80 m posting, measured in isolation:

| | Peak RSS | Wall time |
|---|---:|---:|
| Before | 4.87 GB | 31 s |
| After (512 MB tile budget) | **1.32 GB** | 31 s |
| After (128 MB tile budget) | **1.04 GB** | **19 s** |

Memory fell 3.7× and now tracks the configured budget. The smaller budget is
also *faster* — smaller tiles fit better in cache, so the knob does not trade
speed for memory in the range that matters.

## Measured capacity

All rows: 100 km AOI, 80 m coherence posting (1250 × 1250 px), 4 workers,
512 MB tile budget, measured back-to-back on an otherwise idle machine. The
scenario files pin the worker count rather than defaulting to `cpu_count - 1`,
so `make load-test-full` runs the same shape on a machine with a different core
count instead of quietly running a different experiment.

| Scenario | Items | Pairs/item | Service p50 | Throughput | Peak RSS | Utilization | Capacity | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|:--|
| `steady-cycle-6` | 24 | 24 | 38.1 s | 15.9 MB/s | 6.61 GB | 0.00022 | 19,280 AOIs | **SHIP** |
| `cycle-burst-6` | 24 | 24 | 36.6 s | 16.4 MB/s | 6.61 GB | 0.00021 | 19,859 AOIs | **SHIP** |
| `reprocess-backlog-2` | 8 | 30 | 46.2 s | 16.2 MB/s | 7.93 GB | 0.000036 | 39,279 AOIs | **SHIP** |

Every objective passed on every scenario, with zero failed items.

Throughput is bytes of input per second of *worker* time, scaled by the worker
count — not bytes per second of wall clock. Wall clock would fold in the
compressed arrival spread and make the figure a function of the compression
knob, which is exactly what the harness promises it is not. Capacity is AOIs
carried at the SLO's 0.70 utilization, against each scenario's own deadline
(12 days for a cycle, 30 for the reprocessing campaign).

**What reproduces, and what does not.** Re-running `cycle-burst-6` from the
pinned scenario while the machine was busy with unrelated work gave 40.7 s p50
against the 36.6 s above, capacity 16,758 against 19,859 — about 15% off, with
peak RSS actually *lower* at 4.54 GB because less was resident. Same 24 items,
zero failures, all four objectives PASS.

So the SLO verdicts, the item counts and the order of magnitude of the
utilization reproduce; absolute timings track whatever else the machine is
doing, and should be read with a ±20% band. The steady-versus-burst comparison
below is the part worth trusting most, because both were measured back-to-back
under the same conditions — a difference between them is a real difference,
whereas a difference against a number in this table might just be a busy laptop.

`fine-posting` (20 m posting, 5000 × 5000 px, 2 workers) has no row here. It was
started on a host whose swap was already fully committed by unrelated processes,
ran for 13 minutes without completing its 8 items, and **was stopped rather than
allowed to finish** — a throughput number from a box that is paging describes
the swap subsystem, not the pipeline, and reporting one would be worse than
reporting none.

One measurement from it is sound, because paging changes when memory is resident
but not how much is allocated: **5.04 GB resident for a single 20 m item**
(2.4 GB stack, 2.4 GB deficit array, tile budget on top). That is the number
that pins the worker count and the constraint the scenario exists to expose.
Re-run it on a machine with free RAM for a throughput figure; the memory figure
will not move.

### What the pipeline can reliably handle

**At 80 m posting, compute is nowhere near the constraint, and that is the
headline.** One frame group of a 100 km AOI costs ~38 s of service per 12-day
cycle. A cycle is 1,036,800 seconds. On four workers that is a utilization of
**0.0002** — two hundredths of one percent of the available window.

Extrapolated at the measured rate, four workers carry roughly **19,000 AOIs**
before compute saturates a cycle, or ~15,700 while also absorbing a full
reprocessing campaign. Those numbers are large enough that they should not be
read as a capacity plan — they are a statement that **the compute path is not
what will limit this system.** The unmeasured ingest path is (see below).

### The burst is absorbed with no throughput penalty

`steady-cycle-9` and `cycle-burst-9` offer identical volume; the burst delivers
it into 5% of the window, a 20× higher instantaneous arrival rate. Service time
was unchanged — 38.2 s versus 37.3 s, the burst marginally *faster* and well
inside run-to-run noise. Peak memory was identical to 10 MB.

The only thing that moved was queue latency: p95 of 216 s under burst against
137 s under steady arrivals, which is queueing behaving exactly as queueing
should. Both were measured under a 10,000× compressed arrival rate; at the real
cadence, with utilization at 0.0002, no queue forms at all.

So the spike question has a clean answer: **the pipeline absorbs a cycle's
arrivals delivered 20× faster with no degradation in throughput, memory, or
error rate.** What it cannot do is tell us anything about ASF's ability to serve
those granules that fast, which is a different system and untested here.

### Where it degrades, and where it breaks

- **Memory is the binding constraint, not CPU.** Peak RSS scales with worker
  count times per-item working set. On this 16 GB node, four workers on 80 m
  data sit at 6.6 GB with comfortable headroom. At 20 m posting a single item's
  working set was measured at **5.04 GB** resident — the 2.4 GB stack, a 2.4 GB
  deficit array, and the tile budget on top. Two concurrent items is therefore
  the ceiling on a 16 GB node, and four would swap rather than fail cleanly. The
  `fine-posting` scenario pins workers to 2 for exactly this reason; that pin
  *is* the finding, and 5.04 GB is the number behind it.

  The consequence is stark: moving from 80 m to 20 m posting costs 16× the
  pixels but drops the node from 4 concurrent items to 2, so effective capacity
  falls by roughly 32×. Compute headroom absorbs that easily — but only if the
  memory is there, and per-item working set is what has to shrink first. See the
  streaming fix in the scaling path.
- **Deeper stacks cost proportionally.** The reprocessing scenario's 30-pair
  stacks took 46.3 s against 38.2 s for 24 pairs — 21% more work for 25% more
  data, i.e. linear, as the tiled baseline should be.
- **Per-core throughput is not uniform.** An isolated item on a performance core
  takes ~31 s; the same item under 4-way concurrency takes ~38 s, and under
  9-way concurrency on this 10-core machine it degrades much further as the
  scheduler falls back to efficiency cores and memory bandwidth saturates. Do
  not compute capacity as `isolated_rate × n_cores`.
- **It does not break in these scenarios.** Zero failures across 56 items. The
  failure mode we know exists — memory exhaustion at fine posting on a small
  node — is guarded by the tile budget rather than discovered at runtime.

## Scaling path

The measurement reframes this question. I expected compute to be the wall and
sized the scenarios accordingly; it is not, by four orders of magnitude. So the
scaling path below is mostly about **data movement and memory**, not throughput.

**Today, and up to ~100 AOIs.** No work required. Four workers on one commodity
node clear a cycle's compute in under four minutes. Anyone planning capacity for
this range should be planning storage and egress, not cores.

**100 → 1,000 AOIs.** Still not a compute problem, but it stops being a
single-machine problem for other reasons: 1,000 AOIs × 4 frame groups × a 12-day
cycle is ~16,000 granules a cycle at ~1.9 GB each, which is ~30 TB of transfer
per cycle. The work is packaging rather than algorithms — frame groups are
completely independent, with separate stacks, no shared state and no
cross-item coordination, so this is embarrassingly parallel across machines as
well as processes. What is needed is a queue in front of the workers and per
frame group idempotency, so a retry cannot corrupt a Zarr store. The harness's
`WorkItem` is already the unit a real queue would carry.

**The real constraint: ingest, which this document does not measure.** Every
number above is compute against synthesized stacks. At any interesting scale the
pipeline is dominated by pulling GUNW granules from ASF, and
`understory_core.ingest.fetch_granule` currently does the naive thing —
downloads the whole 1.9 GB HDF5 over HTTPS to read one layer out of it. Two
things would change that, in order of value:

1. **Byte-range reads.** ASF's HTTPS endpoint redirects to CloudFront-backed S3
   objects that honour HTTP range requests, so the coherence layer can be read
   without transferring the rest of the granule. This is the single
   highest-value unimplemented optimization in the project.
2. **In-region S3 direct access.** ASF exposes `s3://` URLs in granule metadata,
   readable from `us-west-2` only, with credentials that expire hourly. Moving
   the pipeline next to the data removes egress entirely.

**Measure this before believing any of it.** `tasks.ingest_task` exists and
measures HDF5 extraction from granules on disk; the network path has no
coverage at all. A capacity claim for the full pipeline cannot be made until it
does.

**The move to 20 m posting is a memory problem, not a throughput one.** If the
fine coherence layer exists (see [APPLICATIONS.md](APPLICATIONS.md) — the
documentation is contradictory and it needs settling against a real granule), it
is 16× the pixels and it is the scientifically necessary one, since roughly 80%
of tropical disturbance events are 0.2–0.5 ha and invisible at 80 m. A 24-pair
100 km stack becomes 2.4 GB, peak working memory roughly twice that, so a 16 GB
node runs **two** concurrent items regardless of core count and cores idle
waiting on RAM. The fix is to stop holding the deficit array resident: it is
consumed tile by tile, so a memory-mapped temporary would decouple worker count
from AOI size entirely. Failing that, the answer is simply a bigger node — and
at these utilizations, one node with more RAM beats many nodes with less.

**Beyond that.** Worth saying plainly: this project does not need continental
scale to answer its question. The benchmark needs tens of well-chosen AOIs with
good ground truth, not thousands of mediocre ones. The measured headroom means
scale is not the risk; the risks are label quality and whether the coherence
signal exists at all. Building for a million AOIs would be building the wrong
thing.

## What is not measured here

Stated explicitly, because a capacity document that overstates its own scope is
worse than none:

- **ASF download throughput, Earthdata auth, S3 credential expiry.** Stacks are
  synthesized at real dimensions. `tasks.ingest_task` measures HDF5 extraction
  against granules already on disk; the network is untested.

  Worse than untested, the ingest path has known correctness gaps that no load
  number here would expose. `fetch_granule` is a single `requests.get` with no
  retry, no backoff, no checksum and no resume, and its cache check is
  `exists() and st_size > 0` — which accepts a truncated response as a valid
  granule. There is no state store of ingested `(track, frame, tier, date)`
  tuples, so retry and backfill have nothing to be idempotent against, and an
  interrupted `CoherenceStack.build` leaves N of M timesteps with no way to
  detect the shortfall while a retry appends duplicates. ASF's temporary S3
  credentials also expire after an hour, so any run longer than that fails
  partway. **These are the largest correctness gaps in the repository**, and
  they matter more than any capacity number in this document.
- **Zarr write throughput.** `CoherenceStack.build` appends per pair to bound
  memory, but the load scenarios exercise detection against in-memory stacks.
- **Real coherence statistics.** Synthetic stacks use a base coherence of 0.35
  with 0.06 spread, chosen to match what the literature reports over closed
  canopy. Real data will have different NaN patterns, and NaN density changes
  `nanmedian` cost.
- **Multi-node anything.** Every number is one machine.
- **Sustained running.** Scenarios are single cycles. Nothing here would catch a
  slow leak across a hundred cycles.
- **Per-item peak RSS.** `ru_maxrss` is a process lifetime high-water mark and
  `ProcessPoolExecutor` reuses workers, so per-item figures in the timings are
  upper bounds, not per-item working sets. The run-level peak the SLO gates on
  comes from the parent's sampler and does not have this problem.
- **A quiet machine.** The test host had ~12 GB of swap committed by unrelated
  processes throughout. The 80 m scenarios fit in RAM regardless and are
  unaffected; the 20 m scenario was measured on a box that was already
  swapping, so treat its timings as a lower bound on a dedicated node rather
  than a property of the pipeline.

## Reproducing

```bash
make load-test        # the burst scenario, ~10 min
make load-test-full   # every scenario, including ones expected to fail
make measure-memory   # recalibrate BASELINE_MEMORY_FACTOR
```

Reports land in `reports/` with the git revision, machine, full run config and
per-item timings embedded. CI runs a small `ci-smoke` scenario on every push —
it protects the *shape* of the capacity story (SLOs pass, nothing errors, memory
stays proportionate to input), not its absolute numbers, since a shared runner
is not the deployment target.
