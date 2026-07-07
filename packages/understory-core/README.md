# understory-core

Application-agnostic NISAR data plumbing. The same code serves a forest in Pará, a right-of-way in Texas, or a construction site anywhere. This should be the most boring, best-tested code in the project.

## Modules

- `aoi` — area-of-interest definitions (geometry + track/frame resolution)
- `discovery` — NISAR granule search via `asf_search`, filtered to interferometric product pairs on the 12-day repeat cycle
- `ingest` — granule retrieval (in-region S3 direct access preferred; download fallback) and coherence-layer extraction
- `stack` — per-pixel coherence time-series stack construction (xarray/dask, Zarr-backed)
- `tiling` — tile grid over an AOI so stack computation parallelizes per tile
- `cache` — local/S3 content-addressed cache so no granule is fetched or processed twice
- `catalog` — STAC metadata over the project's own outputs
