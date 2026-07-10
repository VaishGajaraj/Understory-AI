"""Generate the toy benchmark's coherence stack.

Thin wrapper over understory_detect.synthetic's TOY_SCENE preset: one
persistent ~2 km road (detectable) and one transient rain blob (must be
filtered). Deterministic, ~320 KB, regenerated rather than committed.

Usage: uv run python scripts/make_toy_stack.py [output.zarr]
"""

from __future__ import annotations

import sys
from pathlib import Path

from understory_detect.synthetic import TOY_SCENE, generate_scene

DEFAULT_OUT = Path(__file__).parents[1] / "benchmarks" / "toy" / "data" / "toy-stack.zarr"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = generate_scene(TOY_SCENE)
    ds.to_zarr(out, mode="w")
    print(f"wrote {out} ({ds.coherence.shape}, {ds.coherence.nbytes / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
