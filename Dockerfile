# Understory benchmark runner.
#
# The design target is a single mid-size VM in the data's home region
# (us-west-2) running the whole benchmark from one command:
#
#   docker build -t understory .
#   docker run -v $PWD/benchmarks:/app/benchmarks -v ~/.netrc:/root/.netrc:ro \
#       understory understory-bench benchmarks/toy/config.yaml
#
# Earthdata credentials come from the mounted ~/.netrc; nothing secret is
# baked into the image. CI builds this image on every push.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Dependency layer first so code edits don't bust the resolve cache.
COPY pyproject.toml uv.lock ./
COPY packages/understory-core/pyproject.toml packages/understory-core/pyproject.toml
COPY packages/understory-detect/pyproject.toml packages/understory-detect/pyproject.toml
COPY packages/understory-labels/pyproject.toml packages/understory-labels/pyproject.toml
COPY packages/understory-perf/pyproject.toml packages/understory-perf/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace

COPY packages packages
COPY benchmarks benchmarks
COPY scripts scripts
COPY docs docs
RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["understory-bench", "--help"]
