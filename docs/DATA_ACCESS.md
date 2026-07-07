# Data access

## NISAR (primary input)

NISAR L2 products are free and public, distributed by the Alaska Satellite Facility (ASF) DAAC and stored in AWS (us-west-2).

1. Create a (free) NASA Earthdata account: https://urs.earthdata.nasa.gov/
2. Put credentials in `~/.netrc`:
   ```
   machine urs.earthdata.nasa.gov login <username> password <password>
   ```
3. Discovery uses `asf_search` (no credentials needed to search; needed to retrieve).

**Run in-region.** The archive is hundreds of terabytes; the pipeline is designed for direct S3 access from a VM in us-west-2, streaming only the coherence layer out of each granule. A download-based workflow punishes every experiment — use it only for spot checks.

## Auxiliary inputs

- **ERA5** (precipitation, wind — weather joins for the baseline model): Copernicus CDS account, `cdsapi`.
- **ESA WorldCover** (forest mask): public S3, no credentials.
- **Copernicus DEM** (terrain mask): public, via OpenTopography or AWS Open Data.

## Cost discipline

The design target is that a full two-geography benchmark run costs tens of dollars, not thousands. A mid-size VM in us-west-2 with a few hundred GB of scratch is sufficient; no GPU in v0.
