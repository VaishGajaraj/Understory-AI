# NISAR archive status — first contact notes

**As of 2026-07-06.** Rerun `scripts/probe_archive.py` over any AOI for the current picture; this file records findings that shaped the code, not a live inventory.

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
