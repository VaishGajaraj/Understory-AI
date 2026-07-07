# Understory Benchmark Methodology

**Version 0.1.0 (draft)** — this document is versioned alongside the code because, for a benchmark project, the method is the citable artifact. Reviewers must be able to point at a frozen version; results reports record the methodology version they were produced under.

## 1. Question

> Can NISAR L-band coherence detect documented forest degradation events — how early, at what minimum event size, and at what false-alarm rate?

## 2. Signal

Repeat-pass interferometric coherence change detection on NISAR L2 products, 12-day repeat cycle, consecutive-pass pairs only (longer temporal baselines decorrelate too heavily in forest to be usable in v0).

## 3. Detector under test (v0)

1. **Baseline**: per-pixel rolling robust mean/spread of coherence over the trailing ~8 pairs, computed strictly from prior observations (no leakage). A candidate is a pixel whose coherence falls more than `anomaly_sigma` (default 3.0) robust standard deviations below expectation.
2. **Persistence filter**: candidate recurs in ≥ 2 consecutive pairs.
3. **Spatial clustering**: connected components ≥ 12 pixels.
4. **Geometry**: linearity/elongation score reported per event; threshold disabled by default in v0.

All thresholds live in benchmark config files, never in code.

## 4. Scoring

- **Event-level matching**: greedy one-to-one, detections in descending score order, matched to confirmed labels by centroid distance ≤ 500 m within a temporal window of ± 36 days around the label's date window. Spatial IoU is reported but not required in v0.
- **Metrics**: event precision, recall, F1; median detection latency (first anomalous pair midpoint minus event window start); median lead over the optical alert record (GLAD/RADD/DETER dates for the same events, where available); minimum-detectable-size curve (recall binned by event area).
- Only `confirmed` labels count as positives. Detections matching `rejected` labels are false positives — verified natural decorrelation is exactly what the detector must not fire on.
- Every run emits a machine-readable JSON report. Published tables are generated from reports, never hand-assembled.

## 5. Success and kill criteria (stated before building)

- Precision ≥ ~70% against external ground truth at operationally useful recall.
- Events ≤ ~2 ha detectable.
- Median detection lead over optical alerts in cloudy-season tropics ≥ 3 weeks.

If the numbers land short, the failure analysis is published anyway.

## 6. Known caveats

- **Pre-calibration artifacts**: NISAR products before the calibrated July 2026 stream carry documented radiometric banding. Re-validation on calibrated data is a mandatory gate before any number is treated as final.
- **Ionosphere**: L-band is more susceptible than shorter wavelengths; split-spectrum correction is a v1 item.
- **Terrain**: steep-slope geometric distortion is masked, not modeled, in v0.
- **Latency floor**: the 12-day revisit is a hard floor on detection latency; the project never promises faster than the physics allows.

## Changelog

- **0.1.0** (2026-07): initial draft; matching tolerances and v0 detector defined ahead of first data contact — expect revision on contact.
