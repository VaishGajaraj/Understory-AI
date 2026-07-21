# NISAR archive status — first contact notes

**As of 2026-07-21.** Rerun `scripts/probe_archive.py` over any AOI for the current picture; this file records findings that shaped the code, not a live inventory.

## The calibration gate opened on 2026-07-20

The PROVISIONAL tier was empty at first contact and is not any more. This is the single most consequential change since these notes were written.

- **2026-02-27** — BETA: >100,000 L1–L3 products, acquisitions 2025-10-17 → 2026-01-20. Explicitly not fully calibrated.
- **2026-07-20** — PROVISIONAL: global L-band, all acquisitions from 2026-06-17 forward. "Calibrated and partially validated"; generally meets radiometric and geolocation requirements at lower latitudes where ionospheric variability is low.
- **Q4 2026** — validated reprocessing of the entire science-phase backlog, superseding everything earlier.

So METHODOLOGY.md's re-validation gate is now actionable, and there is a **second gate nobody planned for**: anything published between now and the Q4 reprocessing is still provisional-grade and will be superseded. That reprocessing is also the largest load this project will ever absorb — it is modeled as a scenario in `understory-perf` (`scenarios/reprocess-backlog.yaml`).

Observed granule counts at probe time (CMR): `NISAR_L2_GUNW_PROVISIONAL_V1` 11,165; `NISAR_L2_GUNW_BETA_V1` 10,217. GUNW production is running at roughly 1,100 granules/day at a ~1.9 GB median size.

## Known issues that bite a coherence detector

From ASF's published known-issues list. These are false-alarm sources, not footnotes:

- **BETA has radiometric banding across the swath** from incomplete antenna-pattern removal, described as most apparent over uniform radar cross-section — *tropical forest is the named example.*
- **RFI produces decorrelation streaks**, worst in cross-pol. A streak is what the v0 linearity filter is built to select for.
- **Ionospheric artifacts near solar maximum** leave residual decorrelation streaks, particularly in descending tracks and at higher latitudes.
- **Do not mix BETA and PROVISIONAL in one time series.** Processor differences produce artifacts. `CoherenceStack.build` now refuses a mixed-tier pair list outright, the same way it refuses mixed frame groups.

## Unresolved: the coherence layer's posting

Two documentation passes disagreed on whether GUNW carries coherence magnitude at 20 m as well as 80 m, or whether 80 m is the only geocoded posting (with RIFG at 30 m and GCOV at 20 m). The difference decides whether sub-hectare degradation is visible at all — at 80 m a 1 ha event is one to two pixels.

There is an arithmetic prior, and it favours 80 m: a full frame is ~245 x 264 km, so one 20 m float32 coherence layer would be ~645 MB against a ~1.9 GB median granule. Three such layers would exceed the whole granule. Bet on 80 m — but **settle it with `h5ls` on one real granule rather than with arithmetic or docs.** It is an hour of work and it changes the cost and feasibility of everything downstream by roughly 10x. `understory_core.ingest` walks the product tree instead of hardcoding paths precisely because this keeps moving.

## What the archive actually looks like

- **GUNW granules are pairs.** One L2 GUNW granule is one geocoded interferometric pair; reference and secondary acquisition windows are encoded in the scene name (four timestamps). Discovery parses pairing — it does not construct it. This replaced the original single-acquisition pairing design in `understory_core.discovery`.
- **Three calibration tiers**, as separate CMR collections: `NISAR_L2_GUNW_BETA_V1` (10,217 granules globally at probe time), `..._PROVISIONAL_V1` (empty), `..._V1` validated (empty). The validated tier filling up through late 2026 is the re-validation gate from METHODOLOGY.md becoming actionable.
- **`asf_search` works with `shortName=`** against these collections; the generic `dataset=NISAR` search surfaces only ancillary products (ECMWF soil moisture, clock files) and is not useful for imagery.
- **Distribution**: HTTPS via `nisar.asf.earthdatacloud.nasa.gov` plus direct `s3://sds-n-cumulus-prod-nisar-products/...` URLs in granule metadata — the in-region S3 design in DATA_ACCESS.md is confirmed viable.
- **Useful properties** on each result: `pathNumber` (track), `frameNumber`, `flightDirection`, `startTime`/`stopTime` (reference start → secondary end), `s3Urls`, `sceneName`.

## Coverage found at probe time

- **Amazon basin**: 232 GUNW BETA pairs total, span 2025-10-22 → 2026-01-07, almost all frames having a single pair — not yet stackable. The Novo Progresso benchmark AOI (`benchmarks/amazon-para`) had **zero** GUNW coverage.
- **Best stackable series found**: track 99, frames 76/77 (descending, NW Mexico) — 6 consecutive 12-day pairs, 2025-11-05 → 2026-01-04. Useful as a first real-data engineering target even though it is not a forest benchmark geography.

## Implications for sequencing

1. Ingest development (`extract_coherence` from GUNW HDF5) can proceed now against any BETA granule.
2. The Amazon benchmark waits on backlog reprocessing — poll with the probe script; the moment a Pará frame accumulates ~6+ consecutive pairs, the real benchmark unblocks.
3. Everything computed on BETA products carries the documented radiometric-artifact caveat and must be re-validated on `NISAR_L2_GUNW_V1` when it fills.
