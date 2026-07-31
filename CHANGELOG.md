# Changelog

All notable changes to Understory. The methodology document is versioned
separately (`docs/METHODOLOGY.md` carries its own changelog); label data
releases are tagged `labels-vX.Y.Z` with their changelog in
`packages/understory-labels/data/CHANGELOG.md`.

## v0.2.0 — 2026-07-30

First production-shaped cut: the full pipeline runs end-to-end on synthetic
data in CI, every real-data interface is implemented and tested, and the
operational tooling (watching, containerized runs, capacity gates) exists.
No real-granule benchmark numbers yet — the Amazon AOI still awaits archive
backfill; nothing in this release claims otherwise.

### Pipeline

- Real NISAR discovery against ASF/CMR (GUNW pairs, three calibration tiers),
  with retry/backoff on transient search failures.
- GUNW coherence ingest: HDF5 product-tree walker, cached Earthdata retrieval
  with integrity checks (size + catalog MD5 when published).
- `CoherenceStack.build` for real GUNW series: per-frame alignment, AOI clip,
  Zarr persistence; memory-bounded tiled evaluation (`tiling.py`) with
  tiled-vs-untiled bit-identity tests.
- Forest (ESA WorldCover), terrain (DEM slope), and ERA5 weather joins from
  local rasters/tables; validity masks honored end-to-end.
- Scene-wide anomaly guard: passes whose anomalous fraction exceeds 10% are
  suppressed as environmental (weather/ionosphere) before persistence
  filtering — the diffuse-vs-bounded separation, enforced without weather data.

### Benchmark & science

- Kill criteria as code: PASS / FAIL / INSUFFICIENT_DATA verdict embedded in
  every report; synthetic passes marked "scaffolding, not a claim".
- Confidence calibration table (per-score-bin confirm rate + ECE) in every
  report.
- Width- and fill-aware minimum-detectable-size sweep. Measured v0 synthetic
  floors: ~3.7 ha at full fill; nothing detected at 25% sub-pixel fill —
  dilution, not cluster support, binds for narrow features.
- Publishable Markdown report generation from machine-readable results.
- Benchmark label collections scaffolded: Pará (Imazon/IBAMA), eastern
  woodland (controlled disturbances), mining.

### Operations

- `understory-watch`: cron-able per-AOI coverage watch with state files and
  exit-code signaling.
- Docker runner image (uv-based, creds mounted at runtime), built in CI.
- Capacity harness (`understory-perf`): load/latency gates sized for CI,
  measured results in `docs/PERFORMANCE.md`; exit status is the ship call.
- Uniform `-v/-vv` logging across CLIs.
- Review viewer (`apps/viewer`) over real pipeline output.

## v0.1.0 — 2026-07-06

Initial scaffold: monorepo (uv + Bun workspaces), package architecture with
import-linter contracts, v0 detector (rolling median/MAD baseline +
persistence/cluster/linearity filters), scoring harness, versioned label
schema with review standard, toy benchmark in CI, methodology and governance
documents.
