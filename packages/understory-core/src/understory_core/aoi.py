"""Area-of-interest definitions.

An AOI is a named geometry plus the metadata needed to resolve it to NISAR
track/frame coverage. AOIs are the unit everything else operates on: discovery
finds granules covering an AOI, stacks are built per AOI, benchmarks score per AOI.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


class AreaOfInterest(BaseModel):
    """A named region of interest with a GeoJSON geometry (EPSG:4326)."""

    name: str = Field(description="Short unique slug, e.g. 'para-novo-progresso'")
    description: str = ""
    geometry: dict = Field(description="GeoJSON geometry dict (Polygon/MultiPolygon), EPSG:4326")
    biome: str | None = Field(default=None, description="e.g. 'amazon-moist-forest'")

    model_config = {"frozen": True}

    @property
    def shape(self) -> BaseGeometry:
        return shape(self.geometry)

    @property
    def wkt(self) -> str:
        return self.shape.wkt

    @classmethod
    def from_yaml(cls, path: str | Path) -> AreaOfInterest:
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))
