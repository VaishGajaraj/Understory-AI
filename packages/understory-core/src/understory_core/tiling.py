"""Spatial tiling for memory-bounded processing.

A coherence stack over a real NISAR frame does not fit in working memory: the
rolling-baseline step materializes a (time, y, x, window) array, so peak usage
is roughly ``2 * window_pairs`` times the stack itself. At a 100 m posting a
250 km frame is ~2500x2500 px, and 24 pairs of that is ~600 MB of float32 —
which the baseline turns into ~10 GB.

The baseline is per-pixel along time, so splitting the grid into spatial tiles
is exact rather than approximate: tiling changes peak memory, never results.
This module owns the tile arithmetic; ``understory_detect.baseline`` applies it.

Connected-component labeling is *not* tileable this way (a skid trail crossing
a tile edge would become two events), so it runs on the assembled boolean mask,
which is 4x smaller than the float32 stack it came from.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

# Peak working memory of the rolling baseline, as a multiple of
# ``window_pairs * slab_bytes``.
#
# Reasoning from the source says 2 — the constructed window stack plus the
# deviation from its median. Measuring says otherwise: nanmedian sorts a copy,
# the validity count is another window-sized array, and freed blocks stay in
# the allocator's arenas rather than returning to the OS. Measured factors
# across slab shapes (24x400^2, 24x600^2, 24x800^2, 12x800^2, 36x500^2) were
# 8.25, 9.16, 8.66, 8.24, 9.65. We budget at 10 because the number that matters
# is what the OOM killer sees, and being wrong in this direction is cheap.
#
# Re-derive with scripts/measure_baseline_memory.py after touching baseline.py;
# test_memory_model_is_not_optimistic guards it.
BASELINE_MEMORY_FACTOR = 10

# Default working-memory budget for one tile. Deliberately conservative: it is
# the amount a single worker may use, and load runs put one worker per core.
DEFAULT_TILE_BUDGET_BYTES = 512 * 1024 * 1024

# Never tile below this many pixels on a side — past this point per-tile
# overhead dominates and throughput collapses. This floor OVERRIDES the memory
# budget: a deep enough stack cannot be made to fit, and shrinking tiles to 4x4
# to pretend otherwise would trade a memory problem for a throughput one.
# tile_side_for_budget logs when this happens; budget_is_achievable predicts it.
MIN_TILE_SIDE = 64


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tile:
    """Half-open pixel bounds of one spatial tile: ``[y0:y1, x0:x1]``."""

    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def pixels(self) -> int:
        return self.height * self.width


def baseline_peak_bytes(n_time: int, n_pixels: int, window_pairs: int, itemsize: int = 4) -> int:
    """Predicted peak working memory for the rolling baseline over a slab.

    ``n_pixels`` is the pixel count of the slab (height * width). This is the
    model the tile sizer inverts, and the load harness asserts against.
    """
    return BASELINE_MEMORY_FACTOR * window_pairs * n_time * n_pixels * itemsize


def tile_side_for_budget(
    n_time: int,
    window_pairs: int,
    budget_bytes: int = DEFAULT_TILE_BUDGET_BYTES,
    itemsize: int = 4,
) -> int:
    """Largest square tile side whose baseline fits in ``budget_bytes``.

    Subject to the ``MIN_TILE_SIDE`` floor, which wins. When a deep stack makes
    even a 64-pixel tile exceed the budget, this returns the floor and logs how
    far over it goes — the budget is a target, not a guarantee, and silently
    honouring it by producing 4x4 tiles would trade a memory problem for a
    throughput one. ``budget_is_achievable`` reports the same thing without the
    side effect.
    """
    per_pixel = BASELINE_MEMORY_FACTOR * window_pairs * n_time * itemsize
    if per_pixel <= 0:
        raise ValueError("n_time and window_pairs must be positive")
    side = int(math.sqrt(budget_bytes / per_pixel))
    if side < MIN_TILE_SIDE:
        actual = baseline_peak_bytes(n_time, MIN_TILE_SIDE**2, window_pairs, itemsize)
        logger.warning(
            "tile budget %.1f MB unreachable at %d timesteps x window %d: the smallest "
            "worthwhile tile (%dx%d) needs %.1f MB, %.1fx the budget. Reduce stack depth, "
            "or raise max_working_bytes to match the machine.",
            budget_bytes / 1e6,
            n_time,
            window_pairs,
            MIN_TILE_SIDE,
            MIN_TILE_SIDE,
            actual / 1e6,
            actual / budget_bytes if budget_bytes else float("inf"),
        )
        return MIN_TILE_SIDE
    return side


def budget_is_achievable(
    n_time: int,
    window_pairs: int,
    budget_bytes: int = DEFAULT_TILE_BUDGET_BYTES,
    itemsize: int = 4,
) -> bool:
    """Whether ``budget_bytes`` is reachable without going below the tile floor."""
    per_pixel = BASELINE_MEMORY_FACTOR * window_pairs * n_time * itemsize
    if per_pixel <= 0:
        raise ValueError("n_time and window_pairs must be positive")
    return int(math.sqrt(budget_bytes / per_pixel)) >= MIN_TILE_SIDE


def tile_grid(n_y: int, n_x: int, tile_side: int) -> list[Tile]:
    """Cover an (n_y, n_x) grid with non-overlapping square-ish tiles.

    Edge tiles are smaller. No halo: callers must only use this for operations
    that are independent per pixel.
    """
    if tile_side <= 0:
        raise ValueError(f"tile_side must be positive, got {tile_side}")
    return [
        Tile(y0, min(y0 + tile_side, n_y), x0, min(x0 + tile_side, n_x))
        for y0 in range(0, n_y, tile_side)
        for x0 in range(0, n_x, tile_side)
    ]


def tiles_for_budget(
    n_time: int,
    n_y: int,
    n_x: int,
    window_pairs: int,
    budget_bytes: int = DEFAULT_TILE_BUDGET_BYTES,
    itemsize: int = 4,
) -> list[Tile]:
    """Tile an (n_time, n_y, n_x) stack so each tile's baseline fits the budget.

    Returns a single whole-grid tile when the stack already fits — the untiled
    path is the one-tile case, not a separate code path.
    """
    if baseline_peak_bytes(n_time, n_y * n_x, window_pairs, itemsize) <= budget_bytes:
        return [Tile(0, n_y, 0, n_x)]
    return tile_grid(n_y, n_x, tile_side_for_budget(n_time, window_pairs, budget_bytes, itemsize))
