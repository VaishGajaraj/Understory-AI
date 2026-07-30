# Benchmarks

Each directory is one benchmark: an AOI, a date window, a detector, and a label set, wired together by a `config.yaml` that `understory-bench` runs end-to-end.

- [`toy/`](toy) — miniature synthetic stack + fixture labels, checked into the repo. CI runs this on every commit so "does the pipeline still work" is never a matter of memory. No credentials needed.
- [`amazon-para/`](amazon-para) — Brazilian Amazon with externally documented degradation events (Imazon SAD, IBAMA records). The external ground truth nobody can accuse the project of curating. Labels scaffolded empty until transcription.
- [`eastern-woodland/`](eastern-woodland) — instrumented ground-truth sites with controlled disturbances of known date/size/type. Produces the minimum-detectable-event-size curve. Placeholder AOI until a site partner is confirmed.
- [`amazon-mining/`](amazon-mining) — second config for the same coherence pipeline, focused on artisanal/illegal mining. Config-only until labels exist; does not dilute the Pará logging benchmark.

Real benchmarks need NASA Earthdata credentials — see [docs/DATA_ACCESS.md](../docs/DATA_ACCESS.md). Build stacks with `scripts/build_stack.py`; optionally join forest/terrain masks with `scripts/apply_masks.py`.

Results are re-validated on the calibrated (July 2026+) NISAR stream before being treated as final; pre-calibration archive numbers carry a documented caveat. Sequencing: [docs/ROADMAP.md](../docs/ROADMAP.md).
