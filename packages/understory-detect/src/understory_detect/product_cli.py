"""Unified command line for operators and first-time Understory users."""

from __future__ import annotations

import argparse
import json
import netrc
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from understory_core.aoi import AreaOfInterest
from understory_core.discovery import (
    GUNW_COLLECTIONS,
    GunwPair,
    group_by_frame,
    search_gunw_pairs,
    single_cycle_pairs,
    summarize_coverage,
)
from understory_core.stack import CoherenceStack

from understory_detect.cli import main as benchmark_main


def _check(
    name: str, status: str, message: str, *, remediation: str | None = None
) -> dict[str, str]:
    result = {"name": name, "status": status, "message": message}
    if remediation:
        result["remediation"] = remediation
    return result


def doctor(*, earthdata_path: Path, data_dir: Path, require_earthdata: bool) -> dict[str, Any]:
    """Inspect local prerequisites without contacting a remote service."""
    checks: list[dict[str, str]] = []
    checks.append(
        _check(
            "python",
            "pass" if sys.version_info >= (3, 11) else "fail",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            remediation="Install Python 3.11 or newer." if sys.version_info < (3, 11) else None,
        )
    )

    probe = data_dir
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    writable = probe.exists() and os.access(probe, os.W_OK)
    checks.append(
        _check(
            "data_directory",
            "pass" if writable else "fail",
            f"{probe} is writable" if writable else f"{probe} is not writable",
            remediation="Choose a writable --data-dir." if not writable else None,
        )
    )

    earthdata_status = "warn"
    earthdata_message = f"No Earthdata credentials found at {earthdata_path}"
    remediation = "Add a netrc entry for urs.earthdata.nasa.gov; see docs/DATA_ACCESS.md."
    if earthdata_path.exists():
        try:
            credentials = netrc.netrc(earthdata_path).authenticators("urs.earthdata.nasa.gov")
            if credentials:
                earthdata_status = "pass"
                earthdata_message = "Earthdata netrc entry is present"
                remediation = None
            else:
                earthdata_message = "netrc exists but has no urs.earthdata.nasa.gov entry"
        except (netrc.NetrcParseError, OSError) as error:
            earthdata_status = "fail"
            earthdata_message = f"Earthdata netrc could not be parsed: {error}"
    if require_earthdata and earthdata_status != "pass":
        earthdata_status = "fail"
    checks.append(
        _check(
            "earthdata_credentials",
            earthdata_status,
            earthdata_message,
            remediation=remediation,
        )
    )

    return {
        "schema_version": "1",
        "ready": not any(check["status"] == "fail" for check in checks),
        "checks": checks,
    }


def _render_doctor(result: dict[str, Any]) -> str:
    labels = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    lines = ["Understory environment check"]
    for check in result["checks"]:
        lines.append(f"  {labels[check['status']]:4s}  {check['name']}: {check['message']}")
        if check.get("remediation"):
            lines.append(f"        -> {check['remediation']}")
    lines.append("Ready for requested workflow." if result["ready"] else "Action required.")
    return "\n".join(lines)


def _render_inventory(aoi: AreaOfInterest, summary: dict[str, Any]) -> str:
    lines = [
        f"{aoi.name}: {summary['pair_count']} GUNW pairs ({summary['tier']}), "
        f"{summary['single_cycle_pair_count']} at the 12-day cycle"
    ]
    for frame in summary["frames"]:
        marker = "*" if frame == summary["recommended_frame"] else " "
        lines.append(
            f"{marker} track {frame['track']:3d} frame {frame['frame']:3d} "
            f"{frame['direction'][:4]:4s}: {frame['pair_count']:3d} pairs  "
            f"{frame['first_reference']} .. {frame['last_secondary']}"
        )
    if not summary["frames"]:
        lines.append("  no usable 12-day frame series found")
    elif summary["recommended_frame"]:
        lines.append("* longest current series; freeze track/frame before a benchmark run")
    return "\n".join(lines)


def _add_date_window(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", default="2025-07-01", help="ISO start date")
    parser.add_argument("--end", default=str(date.today()), help="ISO end date")


def _select_frame(
    pairs: list[GunwPair],
    *,
    track: int | None,
    frame: int | None,
    direction: str | None,
) -> tuple[tuple[int, int, str], list[GunwPair], bool]:
    grouped = group_by_frame(single_cycle_pairs(pairs))
    if not grouped:
        raise ValueError("no usable 12-day GUNW frame series found")
    if track is None:
        key, selected = max(grouped.items(), key=lambda item: len(item[1]))
        return key, selected, True

    matches = [
        (key, value)
        for key, value in grouped.items()
        if key[0] == track and key[1] == frame and (direction is None or key[2] == direction)
    ]
    if len(matches) != 1:
        available = ", ".join(str(key) for key in sorted(grouped))
        raise ValueError(
            f"requested track/frame/direction matched {len(matches)} series; available: {available}"
        )
    key, selected = matches[0]
    return key, selected, False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="understory",
        description="Discover NISAR coverage, verify prerequisites, and run Understory benchmarks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Check local prerequisites")
    doctor_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    doctor_parser.add_argument(
        "--require-earthdata",
        action="store_true",
        help="Fail when Earthdata credentials are absent",
    )
    doctor_parser.add_argument(
        "--earthdata-netrc", type=Path, default=Path.home() / ".netrc", help=argparse.SUPPRESS
    )
    doctor_parser.add_argument(
        "--data-dir", type=Path, default=Path("data/scratch"), help="Planned local data directory"
    )

    inventory_parser = subparsers.add_parser(
        "inventory", help="Summarize GUNW coverage for an area of interest"
    )
    inventory_parser.add_argument("aoi", type=Path, help="Path to an AOI YAML file")
    inventory_parser.add_argument("--tier", default="provisional", choices=sorted(GUNW_COLLECTIONS))
    inventory_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    _add_date_window(inventory_parser)

    build_parser = subparsers.add_parser(
        "build-stack", help="Build one frozen 12-day GUNW coherence stack"
    )
    build_parser.add_argument("aoi", type=Path, help="Path to an AOI YAML file")
    build_parser.add_argument("--out", type=Path, required=True, help="Output Zarr store")
    build_parser.add_argument("--tier", default="provisional", choices=sorted(GUNW_COLLECTIONS))
    build_parser.add_argument("--track", type=int, help="Frozen NISAR track")
    build_parser.add_argument("--frame", type=int, help="Frozen NISAR frame")
    build_parser.add_argument("--direction", choices=("ASCENDING", "DESCENDING"))
    build_parser.add_argument("--resolution-m", type=int, choices=(20, 80), default=20)
    build_parser.add_argument("--polarization", choices=("HH", "VV"), default="HH")
    build_parser.add_argument("--min-pairs", type=int, default=4)
    build_parser.add_argument("--cache-dir", type=Path, default=Path("data/scratch/granules"))
    build_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    _add_date_window(build_parser)

    run_parser = subparsers.add_parser("run", help="Run a frozen benchmark configuration")
    run_parser.add_argument("config", type=Path, help="Path to benchmark config.yaml")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        result = doctor(
            earthdata_path=args.earthdata_netrc,
            data_dir=args.data_dir,
            require_earthdata=args.require_earthdata,
        )
        print(json.dumps(result, indent=2) if args.json else _render_doctor(result))
        return 0 if result["ready"] else 2

    if args.command == "inventory":
        try:
            aoi = AreaOfInterest.from_yaml(args.aoi)
            pairs = search_gunw_pairs(
                aoi,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                tier=args.tier,
            )
        except (FileNotFoundError, KeyError, ValueError) as error:
            print(f"inventory failed: {error}", file=sys.stderr)
            return 2
        result = summarize_coverage(pairs, args.tier)
        result.update(
            {
                "aoi": aoi.name,
                "start": args.start,
                "end": args.end,
            }
        )
        print(json.dumps(result, indent=2) if args.json else _render_inventory(aoi, result))
        return 0

    if args.command == "build-stack":
        if (args.track is None) != (args.frame is None):
            print(
                "build-stack failed: --track and --frame must be provided together", file=sys.stderr
            )
            return 2
        try:
            aoi = AreaOfInterest.from_yaml(args.aoi)
            pairs = search_gunw_pairs(
                aoi,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                tier=args.tier,
            )
            frame_key, selected, auto_selected = _select_frame(
                pairs,
                track=args.track,
                frame=args.frame,
                direction=args.direction,
            )
            if len(selected) < args.min_pairs:
                raise ValueError(
                    f"selected series has {len(selected)} pairs; need at least {args.min_pairs}. "
                    "Use --min-pairs 1 only for an engineering smoke test."
                )
            CoherenceStack.build(
                aoi,
                selected,
                args.out,
                cache_dir=args.cache_dir,
                resolution_m=args.resolution_m,
                polarization=args.polarization,
            )
        except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
            print(f"build-stack failed: {error}", file=sys.stderr)
            return 2
        track, frame, direction = frame_key
        result = {
            "schema_version": "1",
            "aoi": aoi.name,
            "output": str(args.out),
            "tier": args.tier,
            "track": track,
            "frame": frame,
            "direction": direction,
            "pair_count": len(selected),
            "auto_selected": auto_selected,
            "resolution_m": args.resolution_m,
            "polarization": args.polarization,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            warning = " (auto-selected; freeze track/frame for research)" if auto_selected else ""
            print(
                f"Wrote {args.out}: {len(selected)} pairs, track {track}, frame {frame}, "
                f"{direction}, {args.resolution_m} m {args.polarization}{warning}"
            )
        return 0

    if args.command == "run":
        return benchmark_main([str(args.config)])
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
