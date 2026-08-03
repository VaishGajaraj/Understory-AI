# sierra-madre-t99 — the paper's primary benchmark

The research paper's AOI ([docs/RESEARCH.md](../../docs/RESEARCH.md)):
Golden Triangle pine-oak, Chihuahua/Durango — documented illegal logging in
a dry open-canopy forest whose high, stable L-band coherence gives the
cleanest decorrelation budget to normalize against.

**Coverage (live-verified 2026-08-02, no credentials needed to re-check):**

```bash
uv run understory inventory benchmarks/sierra-madre-t99/aoi.yaml --tier provisional
```

- track 99, frames 74–76 DESC — 3 consecutive 12-day pairs (Jun 21, Jul 3, Jul 15)
- track 48, frames 14–16 ASC — 3 pairs (independent geometry for the paper's robustness checks)
- no flagged calibration tracks in the AOI; ≥7 pairs expected ~October 2026

## De-risk gates before heavy work (RESEARCH.md table)

Gate 3 is the next credential-free action: overlay OPERA DIST-ALERT and
Hansen GFC v1.13 loss on this AOI for Jun–Aug 2026 and confirm real
disturbance events exist in-window. If the AOI is quiet, repick before
building anything.

## Run (once Earthdata creds exist in ~/.netrc)

```bash
uv run understory build-stack benchmarks/sierra-madre-t99/aoi.yaml \
    --out data/scratch/sierra-madre-t99.zarr \
    --tier provisional --track 99 --frame 75 --direction DESCENDING \
    --min-pairs 3

uv run understory-bench benchmarks/sierra-madre-t99/config.yaml -v
```

Until the DIST-ALERT label join lands, the label collection is empty and
every kill criterion honestly reads `INSUFFICIENT_DATA` — the run still
yields gate 4 (pine-oak coherence vs the estimator noise floor) and the
per-land-cover statistics that form the paper's characterization spine.
