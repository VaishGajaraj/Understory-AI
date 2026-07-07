# Uniform verbs across the whole monorepo (Python + TypeScript).
# CI runs `make check`; muscle memory is identical in every repo.

.PHONY: fmt lint typecheck test check py-fmt py-lint py-typecheck py-test ts-fmt ts-lint ts-typecheck ts-test toy-bench

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
	uv run understory-bench benchmarks/toy/config.yaml
