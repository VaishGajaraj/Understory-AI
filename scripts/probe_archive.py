"""Probe the NISAR GUNW archive over an AOI: what exists, where, at what cadence.

The first question every benchmark geography and every partner watch area
raises is "is there data yet?" — this answers it from the command line without
credentials. As the backlog reprocesses through late 2026, rerunning this shows
frames flipping from beta to validated.

Usage:
    uv run python scripts/probe_archive.py benchmarks/toy/aoi.yaml
    uv run python scripts/probe_archive.py benchmarks/amazon-para/aoi.yaml --tier validated
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import (
    GUNW_COLLECTIONS,
    group_by_frame,
    search_gunw_pairs,
    single_cycle_pairs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("aoi", type=Path, help="Path to an AOI yaml")
    parser.add_argument("--tier", default="beta", choices=sorted(GUNW_COLLECTIONS))
    parser.add_argument("--start", default="2025-07-01", help="ISO date")
    parser.add_argument("--end", default=str(date.today()), help="ISO date")
    args = parser.parse_args()

    aoi = AreaOfInterest.from_yaml(args.aoi)
    pairs = search_gunw_pairs(
        aoi,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        tier=args.tier,
    )
    usable = single_cycle_pairs(pairs)
    print(f"{aoi.name}: {len(pairs)} GUNW pairs ({args.tier}), {len(usable)} at the 12-day cycle")
    for frame_key, frame_pairs in sorted(group_by_frame(usable).items()):
        track, frame, direction = frame_key
        dates = [p.reference_start.date() for p in frame_pairs]
        span = f"{dates[0]} .. {dates[-1]}" if len(dates) > 1 else str(dates[0])
        print(
            f"  track {track:3d} frame {frame:3d} {direction[:4]:4s}: "
            f"{len(frame_pairs):3d} pairs  {span}"
        )
    if not pairs:
        print("  (no coverage yet — the archive is still backfilling; try --tier beta)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
