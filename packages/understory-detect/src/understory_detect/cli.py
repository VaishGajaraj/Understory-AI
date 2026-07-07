"""understory-bench: run a full benchmark from a single config file.

The design target: the entire benchmark runs from one command on a cloud VM,
and a full run costs tens of dollars, not thousands — a benchmark nobody can
afford to reproduce is not a benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel


class BenchmarkConfig(BaseModel):
    """One benchmark = one AOI + one date window + one detector + one label set."""

    name: str
    aoi: str  # path to an AOI yaml, relative to the config file
    start: str  # ISO date
    end: str  # ISO date
    detector: str = "v0-filters"
    labels: str  # path to a label collection (GeoJSON), relative to the config file
    stack_store: str = "data/scratch/{name}.zarr"
    report_out: str = "reports/{name}.json"


def run_benchmark(config_path: Path) -> dict:
    """Discover -> stack -> detect -> score -> report."""
    with open(config_path) as f:
        config = BenchmarkConfig.model_validate(yaml.safe_load(f))
    raise NotImplementedError(
        f"benchmark '{config.name}': wire discovery -> CoherenceStack.build -> "
        "detector.detect -> scoring.score once ingest lands"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="understory-bench",
        description="Run an Understory benchmark end-to-end from a config file.",
    )
    parser.add_argument("config", type=Path, help="Path to a benchmark config.yaml")
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(args.config)
    except NotImplementedError as e:
        print(f"not yet implemented: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
