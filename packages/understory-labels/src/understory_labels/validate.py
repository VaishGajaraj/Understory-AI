"""Validate label data files against the JSON Schema and model invariants.

Run by CI over every file in data/events/; also the contributor-facing check:

    uv run understory-labels-validate data/events/*.geojson
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from understory_labels.events import load_collection

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "disturbance-event.schema.json"


def validate_file(path: Path) -> list[str]:
    """Return a list of human-readable problems (empty = valid)."""
    problems: list[str] = []
    with open(path) as f:
        collection = json.load(f)
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)

    seen_ids: set[str] = set()
    for i, feature in enumerate(collection.get("features", [])):
        props = feature.get("properties") or {}
        for error in validator.iter_errors(props):
            problems.append(f"{path}: feature[{i}]: {error.message}")
        event_id = props.get("id")
        if event_id in seen_ids:
            problems.append(f"{path}: feature[{i}]: duplicate id '{event_id}'")
        if event_id:
            seen_ids.add(event_id)

    if not problems:
        try:
            load_collection(path)
        except (ValueError, KeyError) as e:
            problems.append(f"{path}: {e}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="understory-labels-validate")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    all_problems: list[str] = []
    for path in args.files:
        all_problems.extend(validate_file(path))

    for problem in all_problems:
        print(problem, file=sys.stderr)
    if not all_problems:
        print(f"ok: {len(args.files)} file(s) valid")
    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main())
