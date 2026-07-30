# Understory — agent & contributor guide

## What this is

An open benchmark answering one question: **can NISAR L-band coherence detect documented forest degradation events under closed canopy — how early, at what minimum event size, at what false-alarm rate?** The MVP is the Python benchmark pipeline; everything else is scaffolding until that publishes. Full context: `docs/METHODOLOGY.md` and the project README.

## Philosophy

- As simple as possible, but no simpler. Legible statistics before ML; ML only when the benchmark proves it wins.
- Benchmark results are machine-generated, never hand-assembled.
- No application layer without a named user. No feature in `understory-core` that only one application needs.
- No fallbacks left behind: when an implementation is replaced, delete the old one.
- The label library's integrity outranks everything — its review standard is in `packages/understory-labels/CONTRIBUTING.md`.

## Commands (uniform verbs, see Makefile)

```
make fmt / lint / typecheck / test / check   # check = what CI runs
make py-test                                  # Python only (uv run pytest)
make toy-bench                                # toy benchmark end-to-end
make load-test / load-test-full               # capacity; exit status is the ship call
make measure-memory                           # recalibrate the tiling memory model
```

Python is managed by uv (workspace in root `pyproject.toml`); TypeScript by Bun workspaces + Biome. Git hooks: `lefthook install`.

## Architecture

```
packages/understory-labels   # dataset + schema (imports nothing internal; data is CC-BY 4.0)
packages/understory-core     # NISAR plumbing: discovery, ingest, stacks, tiling (imports nothing internal)
packages/understory-detect   # baselines, filters, scoring harness, CLI (imports core + labels)
packages/understory-perf     # load/latency harness (imports core + detect; nothing imports it)
benchmarks/*                 # config-only: one AOI + window + detector + labels each
apps/viewer                  # TS viewer over real pipeline output (report JSON + alerts GeoJSON)
```

The dependency direction is enforced by import-linter (`[tool.importlinter]` in `pyproject.toml`) — a violation is a lint failure, not a review comment.

Key data structure: `CoherenceStack` (`understory_core/stack.py`) — a Zarr-backed xarray Dataset, dims `(time, y, x)`, of 12-day repeat-pass coherence. Detectors implement the `Detector` protocol (`understory_detect/interface.py`) and are scored by `understory_detect/scoring.py`.

Memory is a first-class constraint, not an afterthought: a year of 20 m coherence over one NISAR frame is ~19 GB. The rolling baseline is evaluated in spatial tiles (`understory_core/tiling.py`) so peak memory follows `BaselineConfig.max_working_bytes` rather than AOI size. Tiling is exact — the baseline is per-pixel along time — and `test_baseline_tiling.py` asserts tiled and untiled results are bit-identical. `BASELINE_MEMORY_FACTOR` is calibrated by measurement, not derived; re-run `make measure-memory` after touching `baseline.py`.

## Conventions

- Python ≥ 3.11, ruff (format + lint), pyright, pytest; type hints on public interfaces; pydantic models frozen for value objects.
- TypeScript strict, Biome (single quotes, no semicolons, kebab-case filenames), Node ≥ 22, `bun test`.
- Thresholds and tunables live in benchmark config YAML, never hardcoded.
- TS types in `apps/viewer/src/types.ts` mirror the JSON Schema in `packages/understory-labels/schema/` — keep them in sync when the schema version bumps.
- Stubs raise `NotImplementedError` with a one-line note on the intended v0 implementation.

## Scope guards

- Defense applications are out of scope for this repo (see the working doc's §10 — deliberately separate identity).
- Deformation/phase-based applications (tailings, subsidence, permafrost) are a different processing stack — do not add them here.
- Pre-calibration NISAR numbers are never final: re-validation on the calibrated (July 2026+) stream is a mandatory gate.
