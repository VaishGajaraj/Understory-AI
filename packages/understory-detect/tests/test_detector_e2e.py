"""End-to-end detector test on an in-memory synthetic stack.

Mirrors the toy benchmark's physics at unit-test scale: a persistent line must
be detected as one event with sensible dates; a one-pass blob must be filtered.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import shape
from understory_core.aoi import AreaOfInterest
from understory_core.stack import CoherenceStack
from understory_detect.detectors import V0FilterDetector

TIMES = pd.date_range("2026-01-01", periods=8, freq="12D")


def synthetic_stack() -> CoherenceStack:
    rng = np.random.default_rng(42)
    n = 40
    values = 0.7 + rng.normal(0, 0.04, size=(len(TIMES), n, n)).astype(np.float32)
    # persistent diagonal line from t5, 2 px wide, 20 px long
    idx = np.arange(10, 30)
    for t in range(5, len(TIMES)):
        values[t, idx, idx] = 0.2
        values[t, idx + 1, idx] = 0.2
    # transient blob at t5 only
    values[5, 2:8, 30:36] = 0.3

    dataset = xr.Dataset(
        {"coherence": (("time", "y", "x"), values)},
        coords={
            "time": TIMES,
            "y": np.linspace(-6.99, -7.01, n),
            "x": np.linspace(-55.01, -54.99, n),
        },
    )
    aoi = AreaOfInterest(
        name="unit-test",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-55.01, -6.99],
                    [-54.99, -6.99],
                    [-54.99, -7.01],
                    [-55.01, -7.01],
                    [-55.01, -6.99],
                ]
            ],
        },
    )
    return CoherenceStack(dataset, aoi)


def test_detects_persistent_line_and_ignores_transient_blob():
    detections = V0FilterDetector().detect(synthetic_stack())
    assert len(detections) == 1
    det = detections[0]

    # The detection sits on the injected line (centroid near the diagonal).
    centroid = shape(det.geometry).centroid
    assert -55.005 < centroid.x < -54.995
    assert -7.005 < centroid.y < -6.995

    # Line appears at t5; persistence confirms it one pass later at t6.
    expected_times = [datetime(2026, 1, 1) + timedelta(days=12 * i) for i in range(8)]
    assert det.first_seen == expected_times[6]
    assert det.last_seen == expected_times[7]
    assert det.persistence_passes == 2
    assert det.score > 0.5
    assert det.area_ha is not None and det.area_ha > 0


def test_quiet_stack_yields_no_detections():
    rng = np.random.default_rng(3)
    n = 30
    values = 0.7 + rng.normal(0, 0.04, size=(len(TIMES), n, n)).astype(np.float32)
    dataset = xr.Dataset(
        {"coherence": (("time", "y", "x"), values)},
        coords={
            "time": TIMES,
            "y": np.linspace(-6.99, -7.01, n),
            "x": np.linspace(-55.01, -54.99, n),
        },
    )
    stack = CoherenceStack(dataset, synthetic_stack().aoi)
    assert V0FilterDetector().detect(stack) == []
