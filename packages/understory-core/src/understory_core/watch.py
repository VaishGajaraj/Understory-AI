"""Watch-area coverage tracking: what NISAR pairs are new over an AOI?

The product's heartbeat while the archive backfills, and the substrate of the
future alert subscription: run it from cron, and the day a watched frame gains
new pairs you know to rebuild the stack and rerun detection.

    uv run understory-watch benchmarks/amazon-para/aoi.yaml
    uv run understory-watch aoi.yaml --state .understory/para.json --fail-on-new

State is one small JSON file per watch: the set of granule ids already seen.
Deleting it simply makes the next run report everything as new.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import (
    GunwPair,
    group_by_frame,
    search_gunw_pairs,
    single_cycle_pairs,
)

logger = logging.getLogger(__name__)

# Exit codes: cron-friendly signaling without parsing stdout.
EXIT_NO_NEW = 0
EXIT_NEW_COVERAGE = 10


class WatchState(BaseModel):
    """Everything the watcher remembers between runs."""

    aoi_name: str
    tier: str = "beta"
    seen_granules: set[str] = Field(default_factory=set)
    last_checked: str | None = None  # ISO datetime of the previous run

    @classmethod
    def load(cls, path: Path, aoi_name: str, tier: str) -> WatchState:
        if path.exists():
            state = cls.model_validate_json(path.read_text())
            if state.aoi_name != aoi_name or state.tier != tier:
                raise ValueError(
                    f"state file {path} tracks {state.aoi_name}/{state.tier}, "
                    f"not {aoi_name}/{tier} — use one state file per watch"
                )
            return state
        return cls(aoi_name=aoi_name, tier=tier)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n")


def check(
    aoi: AreaOfInterest,
    state: WatchState,
    *,
    start: date,
    end: date,
    search_fn: Callable[..., list[GunwPair]] = search_gunw_pairs,
    now: datetime | None = None,
) -> tuple[list[GunwPair], WatchState]:
    """One watch cycle: search, diff against seen granules, update state.

    Returns (new 12-day pairs, updated state). The state update is pure — the
    caller decides when to persist it.
    """
    pairs = single_cycle_pairs(search_fn(aoi, start=start, end=end, tier=state.tier))
    new = [p for p in pairs if p.granule_id not in state.seen_granules]
    updated = state.model_copy(
        update={
            "seen_granules": state.seen_granules | {p.granule_id for p in pairs},
            "last_checked": (now or datetime.now()).isoformat(timespec="seconds"),
        }
    )
    return new, updated


def format_new_coverage(new: list[GunwPair]) -> str:
    lines = [f"{len(new)} new 12-day pair(s):"]
    for frame_key, frame_pairs in sorted(group_by_frame(new).items()):
        track, frame, direction = frame_key
        dates = ", ".join(str(p.reference_start.date()) for p in frame_pairs)
        lines.append(f"  track {track:3d} frame {frame:3d} {direction[:4]:4s}: {dates}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="understory-watch",
        description="Report new NISAR GUNW coverage over an AOI since the last run.",
    )
    parser.add_argument("aoi", type=Path, help="Path to an AOI yaml")
    parser.add_argument("--state", type=Path, default=None, help="State file (JSON)")
    parser.add_argument("--tier", default="beta", choices=["beta", "provisional", "validated"])
    parser.add_argument("--start", default="2025-07-01", help="ISO date search window start")
    parser.add_argument(
        "--fail-on-new",
        action="store_true",
        help=f"Exit {EXIT_NEW_COVERAGE} when new coverage appears (for cron alerting)",
    )
    args = parser.parse_args(argv)

    aoi = AreaOfInterest.from_yaml(args.aoi)
    state_path = args.state or Path(".understory") / f"watch-{aoi.name}-{args.tier}.json"
    state = WatchState.load(state_path, aoi.name, args.tier)
    first_run = state.last_checked is None

    new, updated = check(aoi, state, start=date.fromisoformat(args.start), end=date.today())
    updated.save(state_path)

    if new:
        prefix = "first run — baseline recorded; " if first_run else ""
        print(f"{aoi.name}: {prefix}{format_new_coverage(new)}")
        return EXIT_NEW_COVERAGE if (args.fail_on_new and not first_run) else EXIT_NO_NEW
    print(f"{aoi.name}: no new coverage (tracking {len(updated.seen_granules)} granules)")
    return EXIT_NO_NEW


if __name__ == "__main__":
    raise SystemExit(main())
