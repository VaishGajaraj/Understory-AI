"""understory-load: run a load scenario and emit a machine-generated report.

The report is the artifact. Capacity numbers quoted anywhere else in the
project should be traceable to a report file produced by this command, for the
same reason benchmark tables are generated rather than typed.

    understory-load scenarios/cycle-burst.yaml
    understory-load scenarios/cycle-burst.yaml --out reports/burst.json
    understory-load scenarios/cycle-burst.yaml --n-aoi 50 --workers 8
    understory-load --rescore reports/cycle-burst-9.json   # re-judge, don't re-run

Exit status is the ship / no-ship call: 0 when every objective passes, 1
otherwise, so a scenario can gate a deploy.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from understory_perf import slo, workload
from understory_perf.runner import RunConfig, RunResult, capacity_aoi_count, run

HARNESS_VERSION = "0.1.0"


class ScenarioConfig(BaseModel):
    """One load scenario: a workload shape, a geometry, and a machine size."""

    name: str
    shape: str  # steady-cycle | cycle-burst | reprocess-backlog | aoi-backfill
    n_aoi: int
    stack_depth: int = 24
    posting: str = "coarse"  # coarse = 80 m GUNW, fine = 20 m GUNW
    aoi_side_km: float = 100.0
    workers: int | None = None
    max_working_bytes: int | None = None
    # Model-time compression. 1.0 replays a real 12-day cycle; the default
    # replays the same arrival pattern ~10000x faster so the test is cheap.
    compression: float = 1e-4
    report_out: str | None = None


def _machine() -> dict:
    import os

    info = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
    }
    try:
        import psutil

        info["total_memory_gb"] = round(psutil.virtual_memory().total / 1e9, 2)
    except ImportError:
        info["total_memory_gb"] = None
    return info


def _git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def run_scenario(config: ScenarioConfig) -> dict:
    kwargs: dict = {"compression": config.compression}
    if config.shape in ("steady-cycle", "cycle-burst"):
        kwargs["stack_depth"] = config.stack_depth
    load = workload.build(config.shape, config.n_aoi, **kwargs)

    defaults = RunConfig()
    run_config = RunConfig(
        posting=config.posting,
        aoi_side_km=config.aoi_side_km,
        workers=config.workers or defaults.workers,
        max_working_bytes=config.max_working_bytes or defaults.max_working_bytes,
    )
    result = run(load, run_config)
    verdict = slo.evaluate(result, scenario=config.name)

    return {
        "scenario": config.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "harness_version": HARNESS_VERSION,
        "git_revision": _git_revision(),
        "machine": _machine(),
        "workload": {
            "shape": config.shape,
            "name": load.name,
            "description": load.description,
            "n_items": load.n_items,
            "n_pairs": load.n_pairs,
            "compression": config.compression,
            "notes": load.notes,
        },
        "run": {
            "config": result.config,
            "height_px": result.height_px,
            "width_px": result.width_px,
            **result.summary(),
        },
        "capacity": {
            "aoi_at_full_utilization": _round(capacity_aoi_count(result, 1.0)),
            "aoi_at_slo_utilization": _round(capacity_aoi_count(result, slo.MAX_UTILIZATION)),
        },
        "slo": verdict.model_dump(mode="json"),
        "timings": result.timings,
    }


def rescore(report_path: Path) -> dict:
    """Re-evaluate a stored run against the current SLOs, without re-running it.

    Per-item timings are the expensive part and stay valid; every derived metric
    is a pure function of them. Use this when a threshold changes, or when a
    derived metric turns out to have been computed wrongly.
    """
    report = json.loads(report_path.read_text())
    result = RunResult.from_report(report)
    verdict = slo.evaluate(result, scenario=report["scenario"])
    return {
        **report,
        "rescored_at": datetime.now(UTC).isoformat(),
        "rescored_from": str(report_path),
        "harness_version": HARNESS_VERSION,
        "run": {
            "config": result.config,
            "height_px": result.height_px,
            "width_px": result.width_px,
            **result.summary(),
        },
        "capacity": {
            "aoi_at_full_utilization": _round(capacity_aoi_count(result, 1.0)),
            "aoi_at_slo_utilization": _round(capacity_aoi_count(result, slo.MAX_UTILIZATION)),
        },
        "slo": verdict.model_dump(mode="json"),
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="understory-load",
        description="Run a load scenario against the detection pipeline.",
    )
    parser.add_argument("scenario", type=Path, nargs="?", help="Path to a scenario YAML")
    parser.add_argument(
        "--rescore",
        type=Path,
        help="Re-evaluate a stored report against the current SLOs instead of running",
    )
    parser.add_argument("--out", type=Path, help="Where to write the report JSON")
    parser.add_argument("--n-aoi", type=int, help="Override the AOI count")
    parser.add_argument("--workers", type=int, help="Override the worker count")
    parser.add_argument("--posting", choices=("coarse", "fine"), help="Override GUNW posting")
    args = parser.parse_args(argv)

    if args.rescore:
        report = rescore(args.rescore)
        out = args.out or args.rescore
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"rescored {args.rescore} -> {out}", file=sys.stderr)
        print(json.dumps({k: v for k, v in report.items() if k != "timings"}, indent=2))
        verdict = slo.SloVerdict.model_validate(report["slo"])
        print("\n" + slo.format_table(verdict), file=sys.stderr)
        return 0 if verdict.shippable else 1

    if args.scenario is None:
        parser.error("a scenario YAML is required (see packages/understory-perf/scenarios/)")

    config = ScenarioConfig.model_validate(yaml.safe_load(args.scenario.read_text()))
    if args.n_aoi:
        config = config.model_copy(update={"n_aoi": args.n_aoi})
    if args.workers:
        config = config.model_copy(update={"workers": args.workers})
    if args.posting:
        config = config.model_copy(update={"posting": args.posting})

    report = run_scenario(config)

    out = args.out or (Path(config.report_out) if config.report_out else None)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {out}", file=sys.stderr)

    summary = {k: v for k, v in report.items() if k != "timings"}
    print(json.dumps(summary, indent=2))

    verdict = slo.SloVerdict.model_validate(report["slo"])
    print("\n" + slo.format_table(verdict), file=sys.stderr)
    return 0 if verdict.shippable else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["ScenarioConfig", "asdict", "main", "run_scenario"]
