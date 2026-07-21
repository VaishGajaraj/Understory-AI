# Contributing to Understory

Thanks for your interest. Understory is a benchmark project: the most valuable contributions are competing detectors run against the same scoring harness, verified labels for the event library, and fixes to the data plumbing.

## Ground rules

- Decisions happen in public GitHub issues. Open one before starting anything non-trivial.
- Code is Apache 2.0; label data is CC-BY 4.0. Contributions are accepted under those licenses.
- No application layer without a named user. No feature in `understory-core` that only one application needs.

## Development setup

```bash
# Python (uv manages the workspace)
uv sync
uv run pytest
uv run ruff check .

# TypeScript (Bun workspaces)
bun install
bun run lint && bun run typecheck && bun test

# Everything CI runs, in one verb
make check
```

CI runs the full pipeline on a checked-in toy granule — "does it still work" is never a matter of memory. Your PR must keep that green.

It also runs a small load scenario (`make load-test` uses the full one) and re-checks the tiling memory model. Both guard capacity rather than correctness: a change that quietly makes the detector need ten times the memory passes every unit test and breaks every real run. If you touch `understory_detect/baseline.py`, re-run `make measure-memory` — the tile sizer's constant is calibrated by measurement, not derived, and under-budgeting it OOM-kills runs mid-cycle instead of degrading.

## Contributing a detector

Detectors implement the `Detector` protocol in `understory_detect.interface` and are evaluated by the scoring harness against versioned label releases. Submit the detector, its config, and the generated benchmark report. Hand-edited result tables are not accepted — reports are machine-generated or they don't exist.

## Contributing labels

The label library has its own review standard (what counts as "confirmed", what evidence is required). See [`packages/understory-labels/CONTRIBUTING.md`](packages/understory-labels/CONTRIBUTING.md). Label quality control is editorial work, not code review, and is deliberately stricter.

## Style

- Python: `ruff` for lint + format, type hints on public interfaces, Python ≥ 3.11.
- TypeScript: strict mode, `prettier` formatting, Node ≥ 20.
- Commits: imperative mood, reference the issue.
