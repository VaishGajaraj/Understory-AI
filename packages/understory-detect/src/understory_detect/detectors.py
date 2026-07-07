"""Built-in detectors and the registry the CLI resolves names against.

The v0 detector is the legible reference method: statistical baseline plus
persistence, clustering, and geometry filters. Competing detectors implement
the same ``Detector`` protocol and register here (or are passed directly to
the scoring harness).
"""

from __future__ import annotations

import warnings

from pydantic import BaseModel
from understory_core.stack import CoherenceStack

from understory_detect.baseline import BaselineConfig, anomaly_deficit
from understory_detect.events import extract_events
from understory_detect.filters import FilterConfig, cluster_filter, persistence_filter
from understory_detect.interface import Detection


class V0Config(BaseModel):
    baseline: BaselineConfig = BaselineConfig()
    filters: FilterConfig = FilterConfig()


class V0FilterDetector:
    """Baseline anomaly -> persistence -> clustering -> geometry."""

    name = "v0-filters"
    version = "0.1.0"

    def __init__(self, config: V0Config | None = None):
        self.config = config or V0Config()

    def detect(self, stack: CoherenceStack) -> list[Detection]:
        cfg = self.config
        # Eager per-tile computation: tiles are sized to fit in memory upstream,
        # and eager numpy keeps the early-history all-NaN median warnings
        # suppressible here instead of leaking from a lazy dask graph.
        coherence = stack.coherence.load()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="All-NaN slice encountered")
            deficit = anomaly_deficit(coherence, cfg.baseline)
        candidates = (deficit > cfg.baseline.anomaly_sigma).fillna(False)

        persistent = persistence_filter(candidates, cfg.filters.min_persistence_pairs)
        clustered = cluster_filter(persistent, cfg.filters.min_cluster_pixels)

        events = extract_events(clustered, deficit, id_prefix=f"{self.name}-{stack.aoi.name}")
        return [
            Detection(
                id=e["id"],
                geometry=e["geometry"],
                first_seen=e["first_seen"],
                last_seen=e["last_seen"],
                score=e["score"],
                persistence_passes=e["persistence_passes"],
                area_ha=e["area_ha"],
            )
            for e in events
            if e["linearity"] >= cfg.filters.min_linearity
        ]


REGISTRY: dict[str, type] = {
    V0FilterDetector.name: V0FilterDetector,
}


def build_detector(name: str):
    if name not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown detector '{name}' (known: {known})")
    return REGISTRY[name]()
