# Operator guide

This is the supported path from a fresh checkout to a reproducible Understory run.

## 1. Install

```bash
git clone https://github.com/VaishGajaraj/Understory-AI.git
cd Understory-AI
uv sync
```

## 2. Check the environment

The check is local and does not contact NASA or print credential values.

```bash
uv run understory doctor
uv run understory doctor --require-earthdata --json
```

Earthdata credentials are required for retrieval, not anonymous archive inventory. See
[`DATA_ACCESS.md`](DATA_ACCESS.md).

## 3. Inventory an AOI

```bash
uv run understory inventory benchmarks/amazon-para/aoi.yaml \
  --tier provisional --start 2026-06-17
```

The `*` marks the longest current 12-day series. It is a discovery suggestion, not an experiment
decision. Freeze its track, frame, direction, tier, resolution, polarization, and date window before
a benchmark run. For automation, add `--json`; the inventory output contract is schema version `1`.

## 4. Build a frozen stack

```bash
uv run understory build-stack benchmarks/amazon-para/aoi.yaml \
  --tier provisional --resolution-m 20 --polarization HH \
  --track <track> --frame <frame> \
  --out data/scratch/amazon-para.zarr
```

Use `--min-pairs 1` only for an engineering smoke test. It is not a benchmark.

## 5. Run the benchmark

```bash
uv run understory run benchmarks/amazon-para/config.yaml
```

Each run writes:

- a JSON report with a versioned run manifest;
- a Markdown twin generated from the same report;
- a GeoJSON alert layer for QGIS and other standard GIS tools.

Artifacts are written atomically. A report records the configuration hash, application, software
version, generation time, and available stack provenance.

## 5b. Watch an AOI for new coverage

```
uv run understory-watch benchmarks/amazon-para/aoi.yaml --fail-on-new
```

One JSON state file per (AOI, tier) under `.understory/`; exit 0 = nothing
new, exit 10 = new 12-day pairs appeared (suppressed on the first,
baseline-recording run). Cron pattern: run daily with `--fail-on-new` and
alert on exit 10 — that is the signal to rebuild the stack and rerun
detection. Counts are deduplicated across coverage-variant granules, so
watch, inventory, and build agree.

## 5c. Containerized runs

```
docker build -t understory .
docker run -v $PWD/benchmarks:/app/benchmarks -v ~/.netrc:/root/.netrc:ro \
    understory understory-bench benchmarks/toy/config.yaml
```

Credentials are mounted at runtime; nothing secret is baked in. CI builds
and smoke-runs the image on every push.

## 6. Automate safely

- Treat exit code `0` as success and `2` as an operator/configuration failure.
- Use `--json` for inventory and diagnostics; do not parse the human table.
- Set a unique output directory per run.
- Preserve the config, report, alert layer, stack metadata, and label release together.
- Never combine BETA and PROVISIONAL observations in one series.
- Do not promote an engineering smoke test to a benchmark result.

## Current production gaps

- Retrieval resumes partial HTTP transfers, verifies catalog sizes and available MD5 values, and
  records completed granules in a durable SQLite manifest. Archive records do not always publish a
  checksum, so `checksum_verified=false` remains an explicit provenance state.
- Stack construction appends one pair at a time and can resume only when the frozen frame, tier,
  layer selection, and committed time prefix still match.
- The local viewer supports report inspection and alert triage, but there is no shared review store,
  job queue, hosted API, authentication layer, or operations dashboard.
- Alert review states and held-out real labels are not yet complete.
- Validated NISAR products have not yet been used for a final result.

These are explicit release gates, not hidden limitations. See
[`PRODUCT_STRATEGY.md`](PRODUCT_STRATEGY.md) and [`ROADMAP.md`](ROADMAP.md).
