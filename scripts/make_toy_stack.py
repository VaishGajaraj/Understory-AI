"""Generate the miniature synthetic coherence stack for the toy benchmark.

Injects two anomalies into spatially correlated noise over ~6 timesteps:
- a persistent linear feature matching label `toy-road-001` (detectable), and
- a transient diffuse blob matching `toy-rain-001` (must be filtered out).

Output is small enough to commit (benchmarks/toy/data/toy-stack.zarr) so CI can
run the full pipeline with no credentials and no network.

Usage: uv run python scripts/make_toy_stack.py
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "v0: numpy correlated noise (base coherence ~0.7, sigma ~0.08), "
        "carve the road as a 2-pixel-wide diagonal drop to ~0.2 persisting from "
        "timestep 3 onward, add the rain blob at timestep 3 only, wrap as "
        "xarray with lat/lon coords matching benchmarks/toy/aoi.yaml, write Zarr"
    )


if __name__ == "__main__":
    main()
