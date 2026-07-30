# Performance and capacity

Understory ships a reproducible capacity harness, not a universal throughput claim. Capacity depends
on the machine, selected GUNW layer, AOI size, stack depth, and archive/network behavior. A report is
valid only for the configuration and git revision embedded in that report.

## What is gated

`understory-load` executes the real baseline, anomaly, persistence, and clustering path against
synthetic arrays with explicit NISAR-scale dimensions. It evaluates four service-level objectives:

| Objective | Gate | Why it exists |
|---|---:|---|
| Cycle utilization | <= 0.70 | A 12-day cycle must clear before the next one arrives, with headroom. |
| Alert service-time p95 | <= 5% of the 21-day lead criterion | Engineering delay must not consume the scientific advantage. |
| Peak resident memory | <= 75% of a 16 GB node | Avoid mid-cycle out-of-memory failures. |
| Failure rate | 0% | A silently missing frame group is not an acceptable alerting mode. |

The `ci-smoke` scenario is a short developer regression run. It is intentionally too small, and
GitHub-hosted hardware too variable, to establish deployment capacity. Harness calculations and SLO
evaluation are covered by unit tests on every pull request; capacity runs execute deliberately on the
hardware being evaluated.

## What the harness does not prove

- It does not measure ASF download throughput, Earthdata authentication, redirect behavior, or
  temporary S3-credential renewal.
- It does not establish sensitivity, precision, or recall on real NISAR observations.
- It does not test a multi-node scheduler, hosted API, shared review state, or sustained operation.
- It does not make an 80 m product scientifically interchangeable with the explicitly selected 20 m
  coherence layer.

Retrieval now supports range resume, bounded retries, catalog size and available MD5 verification,
and a durable ingest manifest. Stack construction appends one pair at a time and refuses ambiguous
resume state. Those are correctness controls; network performance still needs a separate measured
scenario using authorized real granules.

## Reproduce a decision

```bash
make load-test
make load-test-full
uv run understory-load --rescore reports/<report>.json
```

Reports contain the scenario, dimensions, worker count, compression factor, machine, git revision,
per-item timings, memory samples, and the generated `PASS`, `FAIL`, or `INSUFFICIENT_DATA` verdict.
Only quote a capacity number when the corresponding report is preserved.

## Production decision

Keep execution as local single-machine batch work until a named pilot supplies a real concurrency,
latency, and retention requirement. Before a hosted release, add a network-ingest scenario, a
sustained multi-cycle soak, and a cost report on the intended deployment hardware. Scale-out is not a
current scientific blocker; real labels and real-data validation are.
