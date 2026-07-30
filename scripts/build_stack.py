"""Build a coherence stack for an AOI from the live NISAR GUNW archive.

Discovers 12-day pairs, picks the frame group with the longest usable series,
extracts coherence, clips to the AOI, and writes a Zarr store that
``understory-bench`` can open.

Requires NASA Earthdata credentials in ~/.netrc for retrieval (search is
anonymous). See docs/DATA_ACCESS.md.

Usage:
    uv run python scripts/build_stack.py benchmarks/amazon-para/aoi.yaml \\
        --out data/scratch/amazon-para.zarr
    uv run python scripts/build_stack.py benchmarks/amazon-para/aoi.yaml \\
        --tier validated --start 2026-07-01
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import (
    GUNW_COLLECTIONS,
    group_by_frame,
    search_gunw_pairs,
    single_cycle_pairs,
)
from understory_core.stack import CoherenceStack

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build_stack")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("aoi", type=Path, help="Path to an AOI yaml")
    parser.add_argument("--out", type=Path, required=True, help="Output Zarr store path")
    parser.add_argument("--tier", default="provisional", choices=sorted(GUNW_COLLECTIONS))
    parser.add_argument("--start", default="2025-07-01", help="ISO date")
    parser.add_argument("--end", default=str(date.today()), help="ISO date")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/scratch/granules"),
        help="Local granule cache",
    )
    parser.add_argument(
        "--min-pairs",
        type=int,
        default=4,
        help="Refuse to build if the longest frame series is shorter than this "
        "(baseline needs history; default matches BaselineConfig.min_history_pairs)",
    )
    parser.add_argument(
        "--track", type=int, help="Freeze one NISAR track instead of auto-selecting"
    )
    parser.add_argument(
        "--frame", type=int, help="Freeze one NISAR frame instead of auto-selecting"
    )
    parser.add_argument(
        "--direction",
        choices=("ASCENDING", "DESCENDING"),
        help="Optional direction when selecting a track/frame",
    )
    parser.add_argument("--resolution-m", type=int, choices=(20, 80), default=20)
    parser.add_argument("--polarization", choices=("HH", "VV"), default="HH")
    args = parser.parse_args()

    if (args.track is None) != (args.frame is None):
        parser.error("--track and --frame must be provided together")

    aoi = AreaOfInterest.from_yaml(args.aoi)
    pairs = search_gunw_pairs(
        aoi,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        tier=args.tier,
    )
    usable = single_cycle_pairs(pairs)
    grouped = group_by_frame(usable)
    if not grouped:
        logger.error(
            "%s: no 12-day GUNW pairs in %s..%s (%s). "
            "Rerun scripts/probe_archive.py; the archive may still be backfilling.",
            aoi.name,
            args.start,
            args.end,
            args.tier,
        )
        return 2

    if args.track is not None:
        matches = [
            (key, value)
            for key, value in grouped.items()
            if key[0] == args.track
            and key[1] == args.frame
            and (args.direction is None or key[2] == args.direction)
        ]
        if len(matches) != 1:
            available = ", ".join(str(key) for key in sorted(grouped))
            logger.error(
                "requested track/frame/direction matched %d series; available: %s",
                len(matches),
                available,
            )
            return 2
        frame_key, frame_pairs = matches[0]
    else:
        frame_key, frame_pairs = max(grouped.items(), key=lambda kv: len(kv[1]))
        logger.warning(
            "auto-selected the longest series; freeze --track/--frame before a benchmark run"
        )
    track, frame, direction = frame_key
    logger.info(
        "using track %d frame %d %s — %d pairs (%s .. %s)",
        track,
        frame,
        direction,
        len(frame_pairs),
        frame_pairs[0].reference_start.date(),
        frame_pairs[-1].secondary_start.date(),
    )
    if len(frame_pairs) < args.min_pairs:
        logger.error(
            "only %d pairs (need >= %d for a usable baseline). Wait for backlog "
            "reprocessing or lower --min-pairs for an engineering smoke test.",
            len(frame_pairs),
            args.min_pairs,
        )
        return 2

    stack = CoherenceStack.build(
        aoi,
        frame_pairs,
        args.out,
        cache_dir=args.cache_dir,
        resolution_m=args.resolution_m,
        polarization=args.polarization,
    )
    coh = stack.coherence
    logger.info(
        "wrote %s  shape=%s  tier(s)=%s",
        args.out,
        dict(coh.sizes),
        stack.dataset.attrs.get("calibration_tiers"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
