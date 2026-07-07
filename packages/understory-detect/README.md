# understory-detect

The science layer: separating human-caused ground disturbance from natural decorrelation in NISAR coherence time series.

## Modules

- `interface` — the pluggable `Detector` protocol. The interface matters more than the first detector being good: it invites competing methods against the same benchmark.
- `baseline` — v0 expected-coherence model: rolling robust mean/variance per pixel per season, conditioned on land cover and recent precipitation.
- `filters` — the three v0 false-alarm cuts, in order of cheapness: persistence across passes, spatial clustering, geometry (linearity/elongation favoring road- and trail-shaped features).
- `events` — grouping surviving anomaly pixels into discrete detection events (polygons with date windows and scores).
- `scoring` — the benchmark harness: event-level precision/recall/F1 with explicit spatial/temporal matching tolerances, detection latency, lead over optical alerts, minimum-detectable-size curves. Every run emits a machine-readable report.
- `cli` — `understory-bench <config.yaml>` runs a full benchmark end-to-end.

ML enters at v1 only if the benchmark shows it beats the filters. The project's credibility rests on a legible method a skeptical remote-sensing reviewer can audit.
