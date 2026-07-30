# Data access

## NISAR (primary input)

NISAR L2 products are free and public, distributed by the Alaska Satellite Facility (ASF) DAAC and stored in AWS (us-west-2).

1. Create a (free) NASA Earthdata account: https://urs.earthdata.nasa.gov/
2. Put credentials in `~/.netrc`:
   ```
   machine urs.earthdata.nasa.gov login <username> password <password>
   ```
3. Discovery uses `asf_search` (no credentials needed to search; needed to retrieve).

**Run in-region.** The archive is hundreds of terabytes; the pipeline is designed for direct S3 access from a VM in us-west-2, streaming only the coherence layer out of each granule. A download-based workflow punishes every experiment — use it only for spot checks. v0 retrieves full granules into a local content-addressed cache (`scripts/build_stack.py`); S3 range reads remain the production target.

**Calibration tiers.** Prefer `validated` (`NISAR_L2_GUNW_V1`) when coverage exists; `beta` / `provisional` results carry the mandatory re-validation caveat in [`METHODOLOGY.md`](METHODOLOGY.md). Probe with:

```bash
uv run python scripts/probe_archive.py benchmarks/amazon-para/aoi.yaml
uv run python scripts/probe_archive.py benchmarks/amazon-para/aoi.yaml --tier validated
```

## Auxiliary inputs

- **ERA5** (precipitation, wind — weather joins for the baseline model): Copernicus CDS account, `cdsapi`. Pre-extract AOI-mean series to CSV/NetCDF with columns `time,precip_mm,wind_ms`, then pass to `understory_core.masks.weather_series` (keeps CI offline).
- **ESA WorldCover** (forest mask): public S3 / ESA downloads, no credentials. Class 10 = tree cover. Local GeoTIFF → `scripts/apply_masks.py --landcover ...`.
- **Copernicus DEM** (terrain mask): public, via OpenTopography or AWS Open Data. Local GeoTIFF → `scripts/apply_masks.py --dem ...`.

## Watch item: OPERA

NASA OPERA produces free analysis-ready surface-disturbance products from Sentinel-1 and (planned) NISAR. If an official NISAR disturbance product line ships, this project should **build on it rather than compete** — free government upstream processing is a gift. Until then, GUNW coherence stacks remain the v0 input. Track releases via the [OPERA project pages](https://www.jpl.nasa.gov/go/opera/) and ASF OPERA collections; note status changes in [`ARCHIVE_STATUS.md`](ARCHIVE_STATUS.md).

## Cost discipline

The design target is that a full two-geography benchmark run costs tens of dollars, not thousands. A mid-size VM in us-west-2 with a few hundred GB of scratch is sufficient; no GPU in v0.
