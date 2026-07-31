# NISAR archive status - first contact notes

**As of 2026-07-30.** Rerun `understory inventory` for the current picture; this file records
findings that shaped the code, not a live inventory.

## Provisional-stream update - 30 July 2026

- The fully calibrated, partially validated `NISAR_L2_GUNW_PROVISIONAL_V1` collection is
  searchable for acquisitions beginning 17 June 2026.
- Pará (`amazon-para`) returns 9 GUNW pairs: 2 are 12-day pairs, but they fall in different frame
  groups. The longest usable per-frame series is still 1 pair.
- Eastern woodland returns 6 pairs (1 usable 12-day pair). Amazon mining returns 12 pairs
  (4 usable), again with only 1 pair per frame group.
- `NISAR_L2_GUNW_V1` remains empty over Pará. No benchmark AOI yet has the 6 consecutive pairs
  needed for baseline history plus persistence.

The archive is no longer empty, so one-pair real-data smoke tests are actionable. A scientific
benchmark verdict remains blocked on time-series depth.

## What the archive actually looks like

- **GUNW granules are pairs.** One L2 GUNW granule is one geocoded interferometric pair;
  reference and secondary acquisition windows are encoded in the scene name. Discovery parses
  pairing - it does not construct it.
- **Three calibration tiers are separate CMR collections:** BETA, PROVISIONAL, and validated V1.
  Do not combine them in one time series.
- **`asf_search` works with `shortName=`** against these collections; a generic dataset search can
  surface ancillary products instead of imagery.
- **Distribution includes HTTPS and direct S3 URLs.** In-region S3 remains the production target;
  local retrieval is the tested engineering path.
- **Useful properties** include path/track, frame, flight direction, reference and secondary
  timestamps, distribution URLs, scene name, file size, and a catalog MD5 when CMR publishes one.

## Product-quality false-alarm sources

- BETA radiometric banding is especially relevant over uniform radar cross-section such as
  tropical forest.
- RFI can produce decorrelation streaks that resemble linear disturbance.
- Residual ionospheric artifacts can also produce decorrelation structure, especially at L-band.
- Processor changes between maturity tiers can resemble landscape change.

These are detector inputs and quality flags, not footnotes. Stack construction rejects mixed
calibration tiers, and final benchmark results must be rerun on validated products.

## Earlier BETA probe

- Amazon-basin coverage was sparse and mostly single-pair per frame.
- Track 99, frames 76/77 over northwest Mexico had six consecutive 12-day BETA pairs and remains a
  useful engineering target, but it is not forest ground truth and cannot answer the benchmark.

## Implications for sequencing

1. Use a PROVISIONAL pair for the real retrieval/extraction/resume smoke test.
2. Continue anonymous inventory polling until one target frame has at least six consecutive pairs.
3. Freeze the product identity before any exploratory benchmark.
4. Treat all BETA-derived behavior as engineering evidence only.
5. Revalidate every published result on validated V1.

## Update — 2026-07-31

The provisional (calibrated) tier arrived: `NISAR_L2_GUNW_PROVISIONAL_V1`
went from empty to **24,134 granules globally, 585 over the Amazon basin**,
spanning acquisitions 2026-06-17 → 2026-07-15. Validated V1 remains empty;
BETA is static (~10,220).

- **First stackable Amazon forest series**: track 89 frame 175 ascending —
  6 consecutive 12-day pairs over closed-canopy western Amazonas. The
  `benchmarks/amazonas-first-light` run targets it.
- Track 46 frames 1–2 (Amazon mouth) also carry 6 pairs each; mixed
  land/water — less useful for the forest baseline.
- **Pará benchmark AOI has its first coverage**: 2 provisional 12-day pairs
  (tracks 103 and 111, one each). Not stackable yet; at mission cadence the
  8-pair baseline window fills around October 2026. `understory-watch
  benchmarks/amazon-para/aoi.yaml --tier provisional --fail-on-new` is the
  trigger.
