# Research plan — THE short-term goal

**Version 0.2.0 (2026-08-02).** The project's short-term goal is one paper:

> **"Understory: Physics-Normalized L-Band Coherence Change Detection for
> Under-Canopy Forest Disturbance — First Results and an Open Benchmark from
> NISAR."**

One IEEE JSTARS submission (methods + early-mission characterization), the
open benchmark as its artifact, an EarthArXiv preprint at submission, and a
short Climate Change AI workshop paper reusing the benchmark. Everything else
in the repo serves this until it ships.

## Thesis (abstract-level)

Raw 12-day L-band coherence is a biased disturbance detector: the
decorrelation budget varies with SNR, geometry, and volume scattering across
a scene. Understory computes a predicted coherence from granule metadata
(γ_SNR x γ_geom x γ_reg x γ_vol x γ_temporal) and tests the residual
(observed − predicted) as a z-score against the estimator's known noise
floor (σ_γ ≈ (1−γ²)/√(2L)), yielding a scene-portable detection statistic.
Applied to consecutive NISAR 12-day pairs over the Sierra Madre Occidental,
validated against OPERA DIST-ALERT and Hansen GFC, against raw-coherence,
intensity, and Sentinel-1 C-band baselines, with an honest
minimum-detectable-clearing-size curve.

## Primary AOI — corrected and live-verified (2026-08-02)

**Sierra Madre Occidental "Golden Triangle" (Chihuahua/Durango pine-oak,
documented illegal logging), NISAR track 99 frames 74–76 descending.**
Live probe: 3 consecutive 12-day pairs per frame (2026-06-21, 07-03, 07-15),
plus track 48 frames 14–16 ascending (3 pairs each) as an independent
geometry. No flagged calibration tracks (161/174, 161/175, 169/090, 169/091)
touch the AOI. ≥7 pairs expected ~October at mission cadence.

Correction recorded: earlier notes said "track 99 = NW Mexico" based on a
Baja California Sur probe — desert, wrong biome. Track 99 also crosses the
mainland pine-oak; the paper AOI is the mainland crossing
(`benchmarks/sierra-madre-t99`). **The Amazon is future work, not v1**:
harder physics (low L-band coherence under humid canopy), thinner coverage,
weaker ground truth. `amazonas-first-light` remains the engineering
shakeout; the Pará benchmark waits for its archive and Imazon/IBAMA labels.

## Ground truth (the 2026 answer)

- **Primary: OPERA DIST-ALERT** — global, 30 m, HLS-based, dry-forest
  capable, peer-reviewed (Pickens et al. 2025, *Nat. Commun.* 16:8948,
  DOI 10.1038/s41467-025-64014-9; product DOI
  10.5067/SNWG/OPERA_L3_DIST-ALERT-HLS_V1.001), in GFW since Jan 2026.
  RADD does **not** cover NW Mexico; free Planet/NICFI ended 2025.
- **Secondary: Hansen GFC v1.13** annual loss (elevated dry-forest error,
  no degradation — reference, not truth).
- Both are optical references to be spot-checked, not ground truth in the
  field sense; the paper says so plainly.

## De-risk gates (verify before committing months)

| # | Gate | Status |
|---|---|---|
| 1 | Extractor agrees with the GUNW coherence layer | **By construction** — the pipeline reads the authoritative GUNW `coherenceMagnitude` directly; only clip/align is ours, covered by bit-identity tests |
| 2 | ≥5–7 usable pairs on a non-flagged track over the AOI | **PASSED 2026-08-02** — 3 pairs today on two independent tracks, ≥7 ~October |
| 3 | DIST-ALERT shows real disturbance in the AOI during the window | **NEXT ACTION** — overlay DIST-ALERT + Hansen on the AOI; kill/repick if quiet |
| 4 | Pine-oak coherence sits well above the ~0.15–0.2 estimator floor (L=25) | Needs first stack — blocked on Earthdata creds |
| 5 | Ionosphere does not dominate the residual at 26°N | Favorable (low latitude, solar-max caveat); check on first stack |

## What the codebase already has vs what the paper needs

Have (paper-ready): authoritative-layer extraction with integrity guards;
resumable frozen-stack builds; tiled memory-bounded baseline; scene guard;
kill-criteria + calibration in every machine-generated report; synthetic
scene generator with width/fill sweeps; WorldCover/DEM/ERA5 joins; the
reproducibility posture (versioned methodology, frozen configs, CI).

Build next, in order:
1. **Physics-normalized detector (v1)** — predicted-coherence budget from
   granule metadata + residual z-score with σ_γ noise floor; registered as
   a second detector through the same harness. *The methods contribution.*
2. **DIST-ALERT ground-truth join** — DIST-ALERT events over an AOI/window
   → label-schema records (`evidence_source: published-record`), plus the
   confusion tables in scoring.
3. **Sentinel-1 C-band coherence baseline** — same AOI/windows through the
   same harness (the #2 reviewer kill reason).
4. **Synthetic injection into real granules** — implant known coherence
   drops into real stacks for ROC/min-size curves; present as
   characterization bounded by the eval-mirror caveat (Section 7 of the
   paper), with DIST-ALERT validation as the independent robustness claim.
5. **Per-land-cover coherence statistics** in the report (the
   early-mission characterization spine; also gate #4).

## Venues and mechanics

- **Primary: IEEE JSTARS** (gold OA, APC $1,800, preprints fine,
  application-tolerant, single/unaffiliated-author feasible).
- **Backup: Science of Remote Sensing** (Elsevier OA). **Stretch: RSE**
  (non-OA route avoids APC). MDPI only if speed becomes everything.
- **Parallel: Climate Change AI workshop** (NeurIPS/ICLR, 4-page,
  non-archival) for the benchmark; NeurIPS D&B track is the ML-venue home
  if pursued (public code + dataset + Croissant metadata).
- **EarthArXiv preprint at submission** (priority defense). Get an ORCID.
- **Recruit one recognized co-author** (JPL/ASF ecosystems or a university
  SAR lab) once preliminary coherence statistics exist — raises acceptance
  odds, converts scoop risk into collaboration. Keep first-authorship.
- Scoop watch: JPL NISAR ecosystems team. If a NISAR forest-coherence paper
  drops, pivot emphasis to the physics-normalized statistic + benchmark
  (idea, not dataset — harder to scoop) and accelerate the preprint.
- Provisional-data caveat: state the CRID, present as early-mission; the
  end-2026 reprocessing campaign supersedes — the validated re-run is the
  revision-stage upgrade.

## Timeline from "first stack built" (~16 weeks)

Weeks 0–2 extractor/stack sanity on real pairs · 2–5 per-land-cover
coherence stats + DIST-ALERT overlay (gates 3–4) · 5–9 physics-normalized
statistic + baselines · 9–12 injection ROC/min-size + false-alarm
arithmetic at swath scale · 12–16 writing, figures, benchmark packaging,
co-author review · week 16 preprint + JSTARS submission. First decision
~4–6 months.

## Standing prerequisites

Earthdata credentials in `~/.netrc` (blocks gates 4–5 and everything after);
a systematic prior-art sweep for the related-work section; ORCID.
