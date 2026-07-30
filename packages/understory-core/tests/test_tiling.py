"""Tiling arithmetic: the thing that decides how large an AOI fits in memory."""

from __future__ import annotations

import pytest
from understory_core.tiling import (
    MIN_TILE_SIDE,
    Tile,
    baseline_peak_bytes,
    tile_grid,
    tile_side_for_budget,
    tiles_for_budget,
)


def test_tile_grid_covers_every_pixel_exactly_once():
    tiles = tile_grid(250, 130, tile_side=64)
    assert sum(t.pixels for t in tiles) == 250 * 130
    covered = {(y, x) for t in tiles for y in range(t.y0, t.y1) for x in range(t.x0, t.x1)}
    assert len(covered) == 250 * 130


def test_tile_grid_edge_tiles_are_clipped_not_overhanging():
    tiles = tile_grid(100, 100, tile_side=64)
    assert max(t.y1 for t in tiles) == 100
    assert max(t.x1 for t in tiles) == 100
    assert Tile(0, 64, 0, 64) in tiles


def test_small_stack_gets_a_single_whole_grid_tile():
    # The untiled path is the one-tile case, not a separate code path.
    tiles = tiles_for_budget(n_time=8, n_y=100, n_x=100, window_pairs=8)
    assert tiles == [Tile(0, 100, 0, 100)]


def test_large_stack_is_split_and_each_tile_fits_the_budget():
    budget = 64 * 1024 * 1024
    tiles = tiles_for_budget(n_time=24, n_y=4000, n_x=4000, window_pairs=8, budget_bytes=budget)
    assert len(tiles) > 1
    for tile in tiles:
        assert baseline_peak_bytes(24, tile.pixels, 8) <= budget


def test_tile_side_never_collapses_below_the_floor():
    # An absurdly small budget must not produce 1x1 tiles, where per-tile
    # overhead would dominate entirely.
    side = tile_side_for_budget(n_time=100, window_pairs=8, budget_bytes=1)
    assert side == MIN_TILE_SIDE


def test_peak_bytes_scales_with_window_and_depth():
    base = baseline_peak_bytes(10, 1000, 8)
    assert baseline_peak_bytes(20, 1000, 8) == 2 * base
    assert baseline_peak_bytes(10, 1000, 16) == 2 * base


def test_zero_window_is_rejected_rather_than_dividing_by_zero():
    with pytest.raises(ValueError):
        tile_side_for_budget(n_time=0, window_pairs=0)


def test_tile_grid_rejects_nonpositive_side():
    with pytest.raises(ValueError):
        tile_grid(10, 10, tile_side=0)


def test_memory_model_is_not_optimistic():
    """The budget must be an over-estimate, never an under-estimate.

    Under-budgeting does not degrade gracefully: tiles come out too large and
    the run is OOM-killed mid-cycle. The constant was calibrated by measurement
    (scripts/measure_baseline_memory.py) at ~9.7 worst case; this guards against
    someone "simplifying" it back to the value the source code implies.
    """
    from understory_core.tiling import BASELINE_MEMORY_FACTOR

    assert BASELINE_MEMORY_FACTOR >= 10, (
        "measured peak is ~9.7x window_pairs x slab bytes; re-run "
        "scripts/measure_baseline_memory.py before lowering this"
    )
