# Roadmap / next steps

Honest sequencing for the **open** NISAR forest-degradation benchmark. Dates are approximate; archive fill rate and partner response dominate the critical path.

## Done (repo state)

- [x] Monorepo scaffold: `understory-core`, `understory-detect`, `understory-labels`, toy benchmark CI
- [x] v0 detector E2E on synthetic toy data (baseline → persistence → cluster → score → kill criteria)
- [x] Real NISAR GUNW discovery (`asf_search` + calibration tiers) and first-contact notes ([`ARCHIVE_STATUS.md`](ARCHIVE_STATUS.md))
- [x] GUNW coherence extraction from HDF5 with local granule cache
- [x] Kill criteria, calibration table, and synthetic size sweeps as code
- [x] `CoherenceStack.build` — clip/align/stack pairs → Zarr (`scripts/build_stack.py`)
- [x] Forest / terrain / ERA5 join APIs on local rasters (`understory_core.masks`, `scripts/apply_masks.py`)
- [x] Markdown twin of every machine-readable benchmark report

## Now (unblocks a real published number)

1. **One-pair PROVISIONAL smoke test** — the 30 July probe found current 12-day products in every benchmark AOI. Run one through extraction, clipping, masking, and GeoJSON export to validate real-data correctness without presenting a benchmark result.
2. **Archive watch** — poll Pará / eastern-woodland AOIs with `scripts/probe_archive.py` until one fixed forest frame has ≥6 consecutive 12-day pairs.
3. **Label transcription** — fill `packages/understory-labels/data/events/amazon-para-imazon.geojson` from published Imazon SAD / IBAMA records (external ground truth). Empty scaffolds are placeholders, not claims.
4. **First real stack** — freeze a track/frame and build a 20 m PROVISIONAL stack; apply forest/terrain masks; run `understory-bench`; treat the report as exploratory.
5. **Validated-stream re-validation** — mandatory gate once `NISAR_L2_GUNW_V1` fills ([`METHODOLOGY.md`](METHODOLOGY.md) caveats).
6. **Partner loop** — one NGO / territorial program, free watch area, QGIS alerts GeoJSON, confirm/reject feedback into the label library ([`WORKING_OPEN.md`](WORKING_OPEN.md) §8).

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
