# understory-core

Application-agnostic NISAR data plumbing. The same code serves a forest in Pará, a right-of-way in Texas, or a construction site anywhere. This should be the most boring, best-tested code in the project.

## Modules

- `aoi` — area-of-interest definitions (geometry + metadata)
- `discovery` — NISAR GUNW search via `asf_search`, calibration tiers, 12-day pair filter, frame grouping
- `ingest` — granule fetch into a local cache + coherence-layer extraction from GUNW HDF5
- `stack` — `CoherenceStack.build` / `open`: clip pairs to an AOI, align on a common grid, write Zarr
- `masks` — forest (WorldCover), terrain (DEM slope), and ERA5 weather joins from local inputs

## Scripts (repo root)

- `scripts/probe_archive.py` — coverage / cadence probe (no credentials for search)
- `scripts/build_stack.py` — discovery → longest frame series → Zarr
- `scripts/apply_masks.py` — join forest/terrain masks onto an existing stack (`valid` variable)
