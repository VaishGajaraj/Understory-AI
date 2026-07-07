"""Pydantic models mirroring schema/disturbance-event.schema.json.

The JSON Schema is the source of truth for contributors and other tooling;
these models must track it. The schema version is checked at load time.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EventClass = Literal[
    "selective-logging",
    "access-road",
    "mining",
    "clearing",
    "controlled-experiment",
    "other",
]

ConfirmationStatus = Literal["confirmed", "rejected", "candidate"]


class DateWindow(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateWindow:
        if self.end < self.start:
            raise ValueError(f"date_window end {self.end} precedes start {self.start}")
        return self


class DisturbanceEvent(BaseModel):
    """One labeled event. Geometry lives on the GeoJSON Feature; everything
    else is the feature's properties."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    geometry: dict
    date_window: DateWindow
    event_class: EventClass
    status: ConfirmationStatus
    biome: str
    evidence_source: str
    area_ha: float | None = Field(default=None, gt=0)
    optical_alert_date: date | None = Field(
        default=None,
        description="First appearance in an optical alert system (GLAD/RADD/DETER), if known",
    )
    notes: str | None = None
    location_precision: Literal["exact", "coarsened"] = "exact"

    model_config = {"frozen": True}

    @classmethod
    def from_feature(cls, feature: dict) -> DisturbanceEvent:
        props = dict(feature.get("properties") or {})
        props.pop("schema_version", None)
        return cls(geometry=feature["geometry"], **props)


def load_collection(path: str | Path) -> list[DisturbanceEvent]:
    """Load every event from a GeoJSON FeatureCollection file."""
    with open(path) as f:
        collection = json.load(f)
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{path}: expected a GeoJSON FeatureCollection")
    return [DisturbanceEvent.from_feature(feat) for feat in collection.get("features", [])]
