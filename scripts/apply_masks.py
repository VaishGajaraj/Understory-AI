"""Join forest/terrain masks onto an existing coherence stack.

Writes a new Zarr (or overwrites) carrying a ``valid`` (y, x) boolean that
``V0FilterDetector`` respects. Requires local WorldCover / DEM GeoTIFFs —
see docs/DATA_ACCESS.md.

Usage:
    uv run python scripts/apply_masks.py data/scratch/aoi.zarr \\
        --aoi benchmarks/amazon-para/aoi.yaml \\
        --landcover data/scratch/worldcover.tif \\
        --dem data/scratch/copernicus-dem.tif \\
        --out data/scratch/aoi-masked.zarr
"""

from __future__ import annotations

import argparse
from pathlib import Path

from understory_core.aoi import AreaOfInterest
from understory_core.masks import combine_masks, forest_mask, terrain_mask
from understory_core.stack import CoherenceStack


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stack", type=Path, help="Input Zarr coherence stack")
    parser.add_argument("--aoi", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--landcover", type=Path, help="ESA WorldCover GeoTIFF")
    parser.add_argument("--dem", type=Path, help="Copernicus DEM GeoTIFF")
    parser.add_argument("--max-slope-deg", type=float, default=20.0)
    args = parser.parse_args()

    if not args.landcover and not args.dem:
        parser.error("provide at least one of --landcover / --dem")

    aoi = AreaOfInterest.from_yaml(args.aoi)
    stack = CoherenceStack.open(args.stack, aoi)
    grid = stack.coherence.isel(time=0)

    masks = []
    if args.landcover:
        masks.append(forest_mask(aoi, grid, landcover=args.landcover))
    if args.dem:
        masks.append(terrain_mask(aoi, grid, dem=args.dem, max_slope_deg=args.max_slope_deg))
    valid = combine_masks(*masks) if len(masks) > 1 else masks[0].rename("valid")
    masked = stack.with_valid_mask(valid)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    masked.dataset.to_zarr(args.out, mode="w")
    print(
        f"wrote {args.out}: {int(valid.sum())}/{valid.size} pixels valid "
        f"({100 * float(valid.mean()):.1f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
