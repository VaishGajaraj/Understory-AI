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

## Now (the research ladder — see [RESEARCH.md](RESEARCH.md))

1. **First-light run** (`benchmarks/amazonas-first-light`) — track 89 frame 175, 3 provisional pairs. Needs only Earthdata creds in `~/.netrc`. Produces the undisturbed-forest coherence noise floor: the first publishable result and the AGU abstract.
2. **AGU Fall 2026 abstract** — deadline **2026-08-05** (requires joining AGU). Fallback: IGARSS 2027.
3. **Label transcription toward ≥50 events** — fill `amazon-para-imazon.geojson` from published Imazon SAD / IBAMA records while Pará coverage accumulates (stackable ~October at mission cadence; `understory-watch --fail-on-new` is the trigger). Ground-truth volume is the #1 reviewer kill reason.
4. **Scored benchmark on provisional** — freeze the Pará frame, build, run, report. Exploratory until validated-tier re-run.
5. **Comparison baselines** — detection lead vs the optical alert record (shipped in the schema) and a Sentinel-1 C-band coherence detector through the same harness (the #2 reviewer kill reason).
6. **Validated-stream re-validation + beta/provisional/validated difference table** once `NISAR_L2_GUNW_V1` fills (Q4 2026) — the #3 reviewer kill reason, quantified.
7. **Partner loop** — one NGO / territorial program, free watch area, QGIS alerts, confirm/reject feedback into the label library.

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
