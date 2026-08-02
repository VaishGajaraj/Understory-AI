# Data access

## NISAR (primary input)

NISAR L2 products are free and public, distributed by the Alaska Satellite Facility (ASF) DAAC and stored in AWS (us-west-2).

1. Create a (free) NASA Earthdata account: https://urs.earthdata.nasa.gov/
2. Put credentials in `~/.netrc`:
   ```
   machine urs.earthdata.nasa.gov login <username> password <password>
   ```
3. Discovery uses `asf_search` (no credentials needed to search; needed to retrieve).

**Run in-region.** The archive is hundreds of terabytes; the pipeline is designed for direct S3 access from a VM in us-west-2, streaming only the coherence layer out of each granule. A download-based workflow punishes every experiment — use it only for spot checks. v0 retrieves full granules into a local content-addressed cache (`uv run understory build-stack ...`); S3 range reads remain the production target.

**Maturity tiers.** Use `provisional` (`NISAR_L2_GUNW_PROVISIONAL_V1`) for current engineering runs and re-run final results on `validated` (`NISAR_L2_GUNW_V1`) when coverage exists. Do not combine BETA and PROVISIONAL observations in one time series because processor changes can resemble landscape change. Probe with the supported CLI (inventory is anonymous and supports `--json`):

```bash
uv run understory inventory benchmarks/amazon-para/aoi.yaml --tier provisional
uv run understory inventory benchmarks/amazon-para/aoi.yaml --tier validated --json
```

Build one explicitly selected 20 m series after choosing a covered frame from the probe output:

```bash
uv run understory build-stack benchmarks/amazon-para/aoi.yaml \
  --tier provisional --resolution-m 20 --polarization HH \
  --track <track> --frame <frame> --out data/scratch/amazon-para.zarr
```

## Auxiliary inputs

- **ERA5** (precipitation, wind — weather joins for the baseline model): Copernicus CDS account, `cdsapi`. Pre-extract AOI-mean series to CSV/NetCDF with columns `time,precip_mm,wind_ms`, then pass to `understory_core.masks.weather_series` (keeps CI offline).
- **ESA WorldCover** (forest mask): public S3 / ESA downloads, no credentials. Class 10 = tree cover. Local GeoTIFF → `scripts/apply_masks.py --landcover ...`.
- **Copernicus DEM** (terrain mask): public, via OpenTopography or AWS Open Data. Local GeoTIFF → `scripts/apply_masks.py --dem ...`.

## Watch item: OPERA

NASA OPERA produces free analysis-ready surface-disturbance products from Sentinel-1 and (planned) NISAR. If an official NISAR disturbance product line ships, this project should **build on it rather than compete** — free government upstream processing is a gift. Until then, GUNW coherence stacks remain the v0 input. Track releases via the [OPERA project pages](https://www.jpl.nasa.gov/go/opera/) and ASF OPERA collections; note status changes in [`ARCHIVE_STATUS.md`](ARCHIVE_STATUS.md).

## Cost discipline

The design target is that a full two-geography benchmark run costs tens of dollars, not thousands. A mid-size VM in us-west-2 with a few hundred GB of scratch is sufficient; no GPU in v0.
