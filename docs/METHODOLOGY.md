# Understory Benchmark Methodology

**Version 0.1.3 (draft)** — this document is versioned alongside the code because, for a benchmark project, the method is the citable artifact. Reviewers must be able to point at a frozen version; results reports record the methodology version they were produced under.

## 1. Question

> Can NISAR L-band coherence detect documented forest degradation events — how early, at what minimum event size, and at what false-alarm rate?

## 2. Signal

Repeat-pass interferometric coherence change detection on NISAR L2 products, 12-day repeat cycle, consecutive-pass pairs only (longer temporal baselines decorrelate too heavily in forest to be usable in v0).

## 3. Detector under test (v0)

1. **Baseline**: per-pixel rolling robust mean/spread of coherence over the trailing ~8 pairs, computed strictly from prior observations (no leakage). A candidate is a pixel whose coherence falls more than `anomaly_sigma` (default 3.0) robust standard deviations below expectation.
2. **Persistence filter**: candidate recurs in ≥ 2 consecutive pairs.
3. **Spatial clustering**: connected components ≥ 12 pixels.
4. **Geometry**: linearity/elongation score reported per event; threshold disabled by default in v0.
5. **Scene guard**: when more than `max_scene_fraction` (default 10%) of scored pixels goes anomalous in one pass, the pass is suppressed wholesale as environmental (rain, soil moisture, ionosphere) before persistence filtering — the diffuse-vs-bounded separation enforced without weather data. A genuine disturbance persisting into clean later passes still confirms there.

All thresholds are serialized in benchmark config files and copied into reports. Code defaults
exist only to make detector construction ergonomic; a publishable benchmark uses the frozen config.

## 4. Scoring

- **Event-level matching**: greedy one-to-one, detections in descending score order, matched to confirmed labels by centroid distance ≤ 500 m within a temporal window of ± 36 days around the label's date window. Spatial IoU is reported (`mean_match_iou`) but not required in v0.
- **Metrics**: event precision, recall, F1; median detection latency (first anomalous pair midpoint minus event window start); median lead over the optical alert record (GLAD/RADD/DETER dates for the same events, where available); minimum-detectable-size curve (recall binned by event area).
- **The lead baseline is the *earliest* alert from any operational system, not GLAD alone.** Global Forest Watch has fused GLAD-L, GLAD-S2, RADD and (since January 2026) DIST-ALERT into a single integrated product, and reports that the integration detects roughly 9 days earlier than any single contributing system. Scoring lead against one stream would therefore flatter Understory by about that margin, and a fifth alert stream that only beats the weakest of four is not worth contributing. Where a label carries alert dates from more than one system, the earliest is the comparator; where only one is available, the report says which, because a lead measured against GLAD-L alone is not the same claim as a lead measured against the integrated product.

  **The label schema cannot yet express this.** `optical_alert_date` is a single date with no system attribution (schema 0.1.0), so today a contributor can record *an* alert date but not *whose*, and the harness cannot tell a GLAD-L date from an integrated-alerts date. Until the schema carries the system — a 0.2.0 change, which also touches `apps/viewer/src/types.ts` — every lead figure must be read as "against whichever system the contributor happened to record". Closing this is a prerequisite for the lead kill criterion to mean what §5 says it means, and it should be closed before any real-data lead number is published.
- Only `confirmed` labels count as positives. Detections matching `rejected` labels are false positives — verified natural decorrelation is exactly what the detector must not fire on.
- Every run emits a machine-readable JSON report. Published tables are generated from reports, never hand-assembled.

## 5. Success and kill criteria (stated before building)

- Precision ≥ 70% against external ground truth at operationally useful recall.
- Events ≤ 2 ha detectable.
- Median detection lead over optical alerts in cloudy-season tropics ≥ 21 days, measured against the earliest available operational alert (see §4) rather than any single system.

These thresholds live in code (`understory_detect.kill_criteria`), are evaluated on every benchmark run, and the go/no-go verdict is embedded in every report — PASS, FAIL, or INSUFFICIENT_DATA per criterion. Verdicts on synthetic benchmarks are explicitly marked as scaffolding, never claims. If the numbers land short on real data, the failure analysis is published anyway.

## 5b. Confidence calibration

Every report includes a calibration table: detections binned by score, with the confirmed-match rate per bin and the expected calibration error. The standard the detector is held to: of detections emitted at ~0.8 score, ~80% should confirm. An overconfident score costs a partner a wasted field trip and is treated as a defect of the same severity as a missed detection.

Known v0 synthetic bounds (`scripts/size_sweep.py`, now swept by width and sub-pixel fill, not just area): with default thresholds (12-pixel cluster minimum, 3σ anomaly), the floor is ~3.7 ha for fully-filling features regardless of width; ~4.9 ha (2 px wide) and ~7.3 ha (1 px wide) at 50% fill; and at 25% fill — a realistic 5 m skid trail in a ~55 m cell — **nothing is detected at any size**, because the diluted coherence drop (0.70 → ~0.58) sits inside the 3σ envelope. Sub-pixel dilution, not cluster support, is the binding constraint for narrow linear features; the minimum-detectable-size claim must therefore be qualified by feature width. The real benchmark explicitly selects the delivered 20 m GUNW coherence grid; silently selecting the 80 m grid would make the 2 ha criterion physically incompatible with the default cluster threshold. Smaller pixels raise fill fractions quadratically in feature width — the strongest single argument for the 20 m grid.

## 6. Known caveats

- **Pre-calibration artifacts**: NISAR products before the calibrated July 2026 stream carry documented radiometric banding. Re-validation on calibrated data is a mandatory gate before any number is treated as final.
- **Ionosphere**: L-band is more susceptible than shorter wavelengths; split-spectrum correction is a v1 item.
- **Terrain**: steep-slope geometric distortion is masked, not modeled, in v0 (`understory_core.masks.terrain_mask`).
- **Forest constraint**: candidates outside forest land cover are suppressed when a WorldCover (or compatible) mask is joined onto the stack (`valid` variable; see `scripts/apply_masks.py`).
- **Latency floor**: the 12-day revisit is a hard floor on detection latency; the project never promises faster than the physics allows.

## Changelog

- **0.1.3** (2026-08): document the scene-wide anomaly guard as detector stage 5; `max_scene_fraction` joins the serialized thresholds in every benchmark config; comparison-baseline plan (optical alert record + Sentinel-1 coherence) recorded in RESEARCH.md.

- **0.1.2** (2026-07): explicitly select the 20 m coherence grid; preserve raster CRS through detection and export alert geometry as EPSG:4326; serialize detector thresholds in benchmark configs and reports.
- **0.1.1** (2026-07): document forest/terrain mask join; reports include mean match IoU and a Markdown twin.
- **0.1.0** (2026-07): initial draft; matching tolerances and v0 detector defined ahead of first data contact — expect revision on contact.
