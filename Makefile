# Uniform verbs across the whole monorepo (Python + TypeScript).
# CI runs `make check`; muscle memory is identical in every repo.

.PHONY: fmt lint typecheck test check py-fmt py-lint py-typecheck py-test ts-fmt ts-lint ts-typecheck ts-test toy-bench load-test load-test-full measure-memory

fmt: py-fmt ts-fmt
lint: py-lint ts-lint
typecheck: py-typecheck ts-typecheck
test: py-test ts-test
check: lint typecheck test

# --- Python (uv workspace) ---
py-fmt:
	uv run ruff format .

py-lint:
	uv run ruff check .
	uv run lint-imports

py-typecheck:
	uv run pyright

py-test:
	uv run pytest

# --- TypeScript (bun workspace) ---
ts-fmt:
	bun run fmt

ts-lint:
	bun run lint

ts-typecheck:
	bun run typecheck

ts-test:
	bun test

# --- Project ---
toy-bench:
	uv run python scripts/make_toy_stack.py
	uv run understory-bench benchmarks/toy/config.yaml
	uv run python scripts/assert_toy_report.py benchmarks/toy/reports/toy.json

# --- Load and capacity ---
# Exit status is the ship / no-ship call: 0 when every SLO passes, 1 otherwise.

SCENARIOS = packages/understory-perf/scenarios

# The burst scenario is the one that matters most and the cheapest to run.
load-test:
	uv run understory-load $(SCENARIOS)/cycle-burst.yaml

# Every scenario, including fine-posting, which is expected to fail its SLOs
# on a single node — that failure is the documented finding, not a regression.
load-test-full:
	uv run understory-load $(SCENARIOS)/steady-cycle.yaml
	uv run understory-load $(SCENARIOS)/cycle-burst.yaml
	uv run understory-load $(SCENARIOS)/reprocess-backlog.yaml
	-uv run understory-load $(SCENARIOS)/fine-posting.yaml

# Recalibrate understory_core.tiling.BASELINE_MEMORY_FACTOR after touching the
# baseline. Fails if the configured budget has become an under-estimate.
measure-memory:
	uv run python scripts/measure_baseline_memory.py
