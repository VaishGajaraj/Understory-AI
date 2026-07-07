# Benchmarks

Each directory is one benchmark: an AOI, a date window, a detector, and a label set, wired together by a `config.yaml` that `understory-bench` runs end-to-end.

- [`toy/`](toy) — miniature synthetic stack + fixture labels, checked into the repo. CI runs this on every commit so "does the pipeline still work" is never a matter of memory. No credentials needed.
- [`amazon-para/`](amazon-para) — Brazilian Amazon with externally documented degradation events (Imazon SAD, IBAMA records). The external ground truth nobody can accuse the project of curating.
- [`eastern-woodland/`](eastern-woodland) — instrumented ground-truth sites with controlled disturbances of known date/size/type. Produces the minimum-detectable-event-size curve.

Real benchmarks need NASA Earthdata credentials — see [docs/DATA_ACCESS.md](../docs/DATA_ACCESS.md).

Results are re-validated on the calibrated (July 2026+) NISAR stream before being treated as final; pre-calibration archive numbers carry a documented caveat.
