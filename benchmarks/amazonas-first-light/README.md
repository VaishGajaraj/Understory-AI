# amazonas-first-light — the first real-data run

The first Amazon forest frame with a stackable calibrated series: **track 89,
frame 175, ascending**, six consecutive 12-day provisional pairs starting
2026-06-17, over closed-canopy moist forest in western Amazonas (Juruá/Jutaí
interfluve).

This is an engineering shakeout, not a scored benchmark. There are no labels
here; every kill criterion will honestly read `INSUFFICIENT_DATA`. What it
produces:

1. Proof the pipeline survives real granules end-to-end.
2. The per-pixel coherence distribution of *undisturbed* closed-canopy forest
   at L-band 12-day repeat — the natural-decorrelation noise floor every
   detector has to beat, measured for the first time on calibrated NISAR data.
3. A false-alarm census: every event the v0 detector emits over intact forest
   is, absent contrary evidence, a false positive worth studying.

## Prerequisite (one-time)

A free NASA Earthdata account, with credentials in `~/.netrc`:

```
machine urs.earthdata.nasa.gov login <username> password <password>
```

## Run it

```bash
# 1. Confirm the series is still there (no credentials needed)
uv run python scripts/probe_archive.py benchmarks/amazonas-first-light/aoi.yaml --tier provisional

# 2. Build the frozen stack (~6 granules, expect a few GB of download)
uv run understory build-stack benchmarks/amazonas-first-light/aoi.yaml \
    --out data/scratch/amazonas-first-light.zarr \
    --tier provisional --track 89 --frame 175 --direction ASCENDING

# 3. Detect + report
uv run understory-bench benchmarks/amazonas-first-light/config.yaml -v
```

Provisional-tier caveat applies: calibrated but not fully validated; final
numbers re-run on `NISAR_L2_GUNW_V1` when it fills (Q4 2026 campaign).
