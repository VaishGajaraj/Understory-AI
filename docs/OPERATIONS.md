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

## 6. Automate safely

- Treat exit code `0` as success and `2` as an operator/configuration failure.
- Use `--json` for inventory and diagnostics; do not parse the human table.
- Set a unique output directory per run.
- Preserve the config, report, alert layer, stack metadata, and label release together.
- Never combine BETA and PROVISIONAL observations in one series.
- Do not promote an engineering smoke test to a benchmark result.

## Current production gaps

- Full-granule retrieval is resumable only at the workflow level, not by byte range.
- Checksums from archive metadata are not yet enforced after download.
- There is no job queue, hosted API, authentication layer, or operations dashboard.
- Alert review states and held-out real labels are not yet complete.
- Validated NISAR products have not yet been used for a final result.

These are explicit release gates, not hidden limitations. See
[`PRODUCT_STRATEGY.md`](PRODUCT_STRATEGY.md) and [`ROADMAP.md`](ROADMAP.md).
