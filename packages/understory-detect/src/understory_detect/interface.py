"""The pluggable detector interface.

Any detector — the v0 statistical filters, a v1 gradient-boosted model, or an
outside researcher's method — implements ``Detector`` and is scored by the same
harness against the same versioned label releases. This interface is the
contract that makes the benchmark a benchmark.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field
from understory_core.stack import CoherenceStack


class Detection(BaseModel):
    """One detected disturbance event."""

    id: str
    geometry: dict = Field(description="GeoJSON geometry (Polygon), EPSG:4326")
    first_seen: datetime = Field(description="Midpoint of the first anomalous pair")
    last_seen: datetime = Field(description="Midpoint of the last anomalous pair")
    score: float = Field(ge=0.0, le=1.0, description="Detector confidence")
    persistence_passes: int = Field(ge=1, description="Consecutive anomalous pairs")
    area_ha: float | None = None

    model_config = {"frozen": True}


@runtime_checkable
class Detector(Protocol):
    """A detector maps a coherence stack to a list of disturbance detections.

    Implementations must be deterministic given (stack, config): benchmark
    results have to be reproducible from a config file and a data reference.
    """

    name: str
    version: str

    def detect(self, stack: CoherenceStack) -> list[Detection]: ...
