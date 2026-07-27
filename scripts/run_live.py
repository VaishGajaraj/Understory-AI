"""Run the pipeline live against the real NISAR archive, end to end.

Discovery -> fetch (resumable, manifest-recorded) -> stack build (idempotent)
-> v0 detector -> alerts GeoJSON the viewer can load. One command:

    uv run python scripts/run_live.py                      # best series, auto
    uv run python scripts/run_live.py --aoi benchmarks/nw-mexico-t99/aoi.yaml
    uv run python scripts/run_live.py --tier provisional --min-pairs 4

This is the engineering path, not a science benchmark: it scores nothing,
because the geographies with stackable series today have no labeled events.
What it proves is the whole real-data plumbing — auth, fetch, HDF5 extraction,
grid alignment, stack build, detection — and it prints where every artifact
landed so `bun run --filter '@understory/viewer' dev` can show the alerts.

Requires NASA Earthdata credentials in ~/.netrc:

    machine urs.earthdata.nasa.gov login <username> password <password>

Create the account at https://urs.earthdata.nasa.gov (free), then accept the
ASF EULA by downloading any granule once in the browser. Without credentials
this stops after discovery with the exact series it would have fetched.
"""

from __future__ import annotations

import argparse
import json
import netrc
import sys
from datetime import date
from pathlib import Path

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import (
    GunwPair,
    group_by_frame,
    search_gunw_pairs,
    single_cycle_pairs,
)
from understory_core.ingest import fetch_granules
from understory_core.stack import CoherenceStack
from understory_detect.cli import detections_to_geojson
from understory_detect.detectors import V0FilterDetector

REPO = Path(__file__).parents[1]
DEFAULT_AOI = REPO / "benchmarks" / "nw-mexico-t99" / "aoi.yaml"
CACHE = REPO / "data" / "scratch" / "granules"
OUT = REPO / "benchmarks" / "nw-mexico-t99" / "reports"


def have_earthdata_credentials() -> bool:
    try:
        auth = netrc.netrc().authenticators("urs.earthdata.nasa.gov")
    except (FileNotFoundError, netrc.NetrcParseError):
        return False
    return auth is not None


def best_series(aoi: AreaOfInterest, tier: str, start: date) -> list[GunwPair]:
    pairs = search_gunw_pairs(aoi, start=start, end=date.today(), tier=tier)
    usable = single_cycle_pairs(pairs)
    groups = group_by_frame(usable)
    if not groups:
        return []
    return max(groups.values(), key=len)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--tier", default="beta", help="beta | provisional | validated")
    parser.add_argument("--start", default="2025-07-01")
    parser.add_argument("--min-pairs", type=int, default=6, help="refuse shallower series")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()

    aoi = AreaOfInterest.from_yaml(args.aoi)
    series = best_series(aoi, args.tier, date.fromisoformat(args.start))
    if len(series) < args.min_pairs:
        print(
            f"{aoi.name}: deepest {args.tier} series is {len(series)} single-cycle pairs, "
            f"below --min-pairs {args.min_pairs}. The forward PROVISIONAL stream adds one "
            "pair per frame per 12 days; re-run scripts/probe_archive.py to watch it fill.",
            file=sys.stderr,
        )
        return 2

    track, frame, direction = series[0].frame_key
    total_gb = sum(p.size_bytes or 0 for p in series) / 1e9
    print(f"{aoi.name}: track {track} frame {frame} {direction}, {len(series)} pairs")
    print(f"  {series[0].reference_start.date()} .. {series[-1].secondary_start.date()}")
    print(f"  transfer: ~{total_gb:.1f} GB" if total_gb else "  transfer: size unknown from CMR")

    if not have_earthdata_credentials():
        print(
            "\nNo Earthdata credentials in ~/.netrc — stopping before download.\n"
            "  machine urs.earthdata.nasa.gov login <user> password <pass>\n"
            "Then re-run; fetches are resumable and recorded, so a retry costs nothing.",
            file=sys.stderr,
        )
        return 3

    print(f"\nfetching {len(series)} granules into {CACHE} ...")
    fetch_granules(series, CACHE, max_workers=args.max_workers)

    store = OUT.parent / "data" / f"{aoi.name}-t{track}f{frame}.zarr"
    store.parent.mkdir(parents=True, exist_ok=True)
    print(f"building stack at {store} ...")
    stack = CoherenceStack.build(aoi, series, store, cache_dir=CACHE)
    shape = dict(stack.dataset.sizes)
    spacing_m = abs(float(stack.dataset.x[1] - stack.dataset.x[0]))
    print(f"  stack {shape}, x-spacing {spacing_m:.1f} (CRS units) — records the real posting")

    print("running v0 detector ...")
    detections = V0FilterDetector().detect(stack)
    OUT.mkdir(parents=True, exist_ok=True)
    alerts = OUT / f"{aoi.name}-alerts.geojson"

    class _Report:
        benchmark = aoi.name
        detector = "v0-filters"
        detector_version = "0.1.0"
        methodology_version = "0.1.0"

    alerts.write_text(json.dumps(detections_to_geojson(detections, _Report()), indent=2) + "\n")
    print(f"\n{len(detections)} detections -> {alerts}")
    print(
        "view: bun run --filter '@understory/viewer' dev  then "
        f"http://localhost:5173/?alerts=/{alerts.relative_to(REPO)}"
    )
    print(
        "\nNOTE: unlabeled geography — nothing here is scored, and BETA-tier products carry "
        "the radiometric-artifact caveat from docs/ARCHIVE_STATUS.md. This run proves the "
        "plumbing, not the science."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
