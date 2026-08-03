# Roadmap / next steps

Honest sequencing for the **open** NISAR forest-degradation benchmark. Dates are approximate; archive fill rate and partner response dominate the critical path.

## Done (repo state)

- [x] Monorepo scaffold: `understory-core`, `understory-detect`, `understory-labels`, toy benchmark CI
- [x] v0 detector E2E on synthetic toy data (baseline → persistence → cluster → score → kill criteria)
- [x] Real NISAR GUNW discovery (`asf_search` + calibration tiers) and first-contact notes ([`ARCHIVE_STATUS.md`](ARCHIVE_STATUS.md))
- [x] GUNW coherence extraction from HDF5 with local granule cache
- [x] Kill criteria, calibration table, and synthetic size sweeps as code
- [x] `CoherenceStack.build` — clip/align/stack pairs → Zarr (`understory build-stack`)
- [x] Forest / terrain / ERA5 join APIs on local rasters (`understory_core.masks`, `scripts/apply_masks.py`)
- [x] Markdown twin of every machine-readable benchmark report
- [x] Unified operator CLI for environment diagnostics, JSON archive inventory, and benchmark runs
- [x] Versioned run manifest with config hash, software version, application, and stack provenance
- [x] Resumable range downloads, catalog size/checksum verification, and a durable ingest manifest
- [x] Incremental, resumable Zarr stack construction with bounded spatial chunks
- [x] Synthetic NISAR-scale capacity/SLO harness and a local report/alert review viewer
- [x] Production and NISAR opportunity strategy grounded in official product boundaries

## Now — THE short-term goal: the JSTARS paper ([RESEARCH.md](RESEARCH.md))

Primary AOI: `benchmarks/sierra-madre-t99` (Golden Triangle pine-oak, track 99 — live-verified, gate 2 passed). The Amazon is future work; `amazonas-first-light` stays as the engineering shakeout.

1. **Gate 3 (credential-free, this week)** — overlay OPERA DIST-ALERT + Hansen GFC on the sierra-madre AOI, Jun–Aug 2026; confirm real events exist in-window. Kill/repick if quiet.
2. **First real stack** (needs Earthdata `~/.netrc`) — build track 99 frame 75; gates 4–5 (pine-oak coherence vs the ~0.15–0.2 estimator floor; ionosphere check at 26°N) + per-land-cover coherence statistics (the characterization spine, and an AGU/CCAI abstract on its own).
3. **Physics-normalized detector (v1)** — predicted-coherence budget (γ_SNR·γ_geom·γ_reg·γ_vol·γ_temporal) from granule metadata; residual z-score vs σ_γ=(1−γ²)/√(2L); registered as a second detector through the same harness. *The methods contribution.*
4. **DIST-ALERT ground-truth join** — AOI/window events → label records (`published-record`), confusion tables in scoring.
5. **Sentinel-1 C-band coherence baseline** through the same harness; raw-coherence and intensity baselines from what exists.
6. **Synthetic injection into real granules** — ROC / minimum-detectable-clearing-size, presented as characterization bounded by the eval-mirror caveat.
7. **Write + ship**: figures, benchmark packaging, one recognized co-author review, EarthArXiv preprint, JSTARS submission (~week 16 from first stack).

## Next (after first real report)

- Eastern-woodland controlled disturbances for the ≤2 ha kill criterion (synthetic bound today is ~3.7 ha at default cluster size).
- Mining as a second **benchmark config** (same pipeline; class `mining` already in the label schema) — only once labels exist.
- Weather-conditioned baseline if the unconditioned v0 fails on real tropics.
- OPERA watch: if NASA ships an official NISAR disturbance product, build on it rather than compete ([`DATA_ACCESS.md`](DATA_ACCESS.md)).
- Ionosphere / split-spectrum corrections — v1 item; document failures honestly until then.

## Explicitly out of scope for this repo

- Defense product identity, CoT/TAK delivery, SBIR scaffolding — companion note only: [`WORKING_DEFENSE.md`](WORKING_DEFENSE.md).
- Phase-based deformation stacks (tailings, subsidence, permafrost) — different processing chain.
- Application layers without a named user; features in `understory-core` that only one app needs.
