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
from understory_core.aoi import AreaOfInterest
from understory_core.stack import CoherenceStack
from understory_labels import __version__ as labels_version
from understory_labels.events import load_collection

from understory_detect import kill_criteria
from understory_detect.detectors import build_detector
from understory_detect.scoring import score

METHODOLOGY_VERSION = "0.1.0"


class BenchmarkConfig(BaseModel):
    """One benchmark = one AOI + one date window + one detector + one label set."""

    name: str
    aoi: str  # path to an AOI yaml, relative to the config file
    start: str  # ISO date
    end: str  # ISO date
    detector: str = "v0-filters"
    labels: str  # path to a label collection (GeoJSON), relative to the config file
    stack_store: str  # path to the coherence stack (Zarr), relative to the config file
    report_out: str  # where to write the report JSON, relative to the config file
    # Synthetic benchmarks exercise the pipeline; their kill-criteria passes
    # are scaffolding, never claims, and reports say so.
    synthetic: bool = False


def run_benchmark(config_path: Path) -> dict:
    """Open stack -> detect -> score -> kill-criteria verdict -> report + alerts."""
    with open(config_path) as f:
        config = BenchmarkConfig.model_validate(yaml.safe_load(f))
    base = config_path.parent

    aoi = AreaOfInterest.from_yaml(base / config.aoi)
    labels = load_collection(base / config.labels)

    store = base / config.stack_store
    if not store.exists():
        raise FileNotFoundError(
            f"coherence stack not found at {store} — for the toy benchmark run "
            "`uv run python scripts/make_toy_stack.py` first; real benchmarks "
            "build stacks via understory_core (see docs/DATA_ACCESS.md)"
        )
    stack = CoherenceStack.open(store, aoi)

    detector = build_detector(config.detector)
    detections = detector.detect(stack)

    report = score(
        detections,
        labels,
        benchmark=config.name,
        detector=detector.name,
        detector_version=detector.version,
        labels_version=labels_version,
        methodology_version=METHODOLOGY_VERSION,
    )
    verdict = kill_criteria.evaluate(report, synthetic=config.synthetic)

    report_dict = report.model_dump(mode="json")
    report_dict["kill_criteria"] = verdict.model_dump(mode="json")
    report_dict["detections"] = [d.model_dump(mode="json") for d in detections]

    out = base / config.report_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report_dict, indent=2) + "\n")

    # QGIS-loadable alert layer next to the report — the format partners
    # already use, per the theory of change.
    alerts_out = out.with_name(f"{config.name}-alerts.geojson")
    alerts_out.write_text(json.dumps(detections_to_geojson(detections, report), indent=2) + "\n")
    return report_dict


def detections_to_geojson(detections: list, report) -> dict:
    """Detections as a GeoJSON FeatureCollection, highest score first."""
    return {
        "type": "FeatureCollection",
        "properties": {
            "benchmark": report.benchmark,
            "detector": f"{report.detector} {report.detector_version}",
            "methodology_version": report.methodology_version,
        },
        "features": [
            {
                "type": "Feature",
                "geometry": d.geometry,
                "properties": {
                    "id": d.id,
                    "score": d.score,
                    "first_seen": d.first_seen.isoformat(),
                    "last_seen": d.last_seen.isoformat(),
                    "persistence_passes": d.persistence_passes,
                    "area_ha": d.area_ha,
                },
            }
            for d in sorted(detections, key=lambda d: -d.score)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="understory-bench",
        description="Run an Understory benchmark end-to-end from a config file.",
    )
    parser.add_argument("config", type=Path, help="Path to a benchmark config.yaml")
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(args.config)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    summary = {k: v for k, v in report.items() if k != "detections"}
    print(json.dumps(summary, indent=2))
    verdict = kill_criteria.KillCriteriaVerdict.model_validate(report["kill_criteria"])
    print(
        f"\n{report['benchmark']}: precision {report['event_precision']:.2f}, "
        f"recall {report['event_recall']:.2f}, f1 {report['f1']:.2f} "
        f"({report['n_detections']} detections vs {report['n_events']} confirmed events)\n"
        + kill_criteria.format_table(verdict),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
