"""Synthetic coherence scene generator.

Plants disturbances of known shape, size, date, and depth into realistic
per-pixel noise, and emits the matching ground-truth labels. Three jobs:

1. CI fixture — the toy benchmark runs the full pipeline on a generated scene.
2. Detector development loop — iterate before real granules flow.
3. Minimum-detectable-size probing — sweep planted sizes against the detector
   (scripts/size_sweep.py) to chart where detection fails.

Standing caveat, inherited deliberately: synthetic results are scaffolding,
never claims. Published numbers come from real granules and external ground
truth only.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd
import xarray as xr
from pydantic import BaseModel, Field


class PlantedDisturbance(BaseModel):
    """One disturbance injected into a synthetic scene."""

    id: str
    shape: Literal["line", "blob"]
    # Center in scene fractional coordinates (0..1 across the grid).
    center: tuple[float, float] = (0.5, 0.5)
    # line: length in pixels along a diagonal, 2 px wide.
    # blob: side of a square patch in pixels.
    size_px: int = 20
    coherence: float = 0.2  # coherence inside the disturbance
    from_step: int = 5  # first timestep the disturbance is present
    persistent: bool = True  # False = present at from_step only (weather-like)

    model_config = {"frozen": True}


class SceneConfig(BaseModel):
    """A synthetic scene: grid, cadence, noise, and planted disturbances."""

    n_pixels: int = 100
    n_steps: int = 8
    start: date = date(2025, 12, 13)
    lon_min: float = -55.025
    lon_max: float = -54.975
    lat_min: float = -7.025
    lat_max: float = -6.975
    base_coherence: float = 0.70
    pixel_sigma: float = 0.03  # static per-pixel variation
    temporal_sigma: float = 0.05  # per-observation noise
    seed: int = 1734
    disturbances: list[PlantedDisturbance] = Field(default_factory=list)

    model_config = {"frozen": True}

    def times(self) -> pd.DatetimeIndex:
        return pd.date_range(str(self.start), periods=self.n_steps, freq="12D")


def generate_scene(config: SceneConfig) -> xr.Dataset:
    """Generate the coherence stack for a scene config. Deterministic per seed."""
    rng = np.random.default_rng(config.seed)
    n = config.n_pixels
    lons = np.linspace(config.lon_min, config.lon_max, n)
    lats = np.linspace(config.lat_max, config.lat_min, n)  # north-up raster order

    base = config.base_coherence + rng.normal(0, config.pixel_sigma, size=(n, n))
    coherence = base[None, :, :] + rng.normal(0, config.temporal_sigma, size=(config.n_steps, n, n))

    for disturbance in config.disturbances:
        ys, xs = _footprint(disturbance, n)
        last_step = config.n_steps if disturbance.persistent else disturbance.from_step + 1
        for t in range(disturbance.from_step, last_step):
            coherence[t, ys, xs] = disturbance.coherence + rng.normal(0, 0.03, size=len(ys))

    return xr.Dataset(
        {"coherence": (("time", "y", "x"), np.clip(coherence, 0.0, 1.0).astype(np.float32))},
        coords={"time": config.times(), "y": lats, "x": lons},
        attrs={
            "title": "Understory synthetic coherence scene",
            "crs": "EPSG:4326",
            "generator": "understory_detect.synthetic",
            "seed": config.seed,
        },
    )


def truth_features(config: SceneConfig) -> list[dict]:
    """GeoJSON Features (label-schema properties) for each planted disturbance.

    Persistent disturbances become confirmed events; transient ones become
    rejected events (verified natural decorrelation) — mirroring how a field
    partner would label them.
    """
    n = config.n_pixels
    lons = np.linspace(config.lon_min, config.lon_max, n)
    lats = np.linspace(config.lat_max, config.lat_min, n)
    features = []
    for disturbance in config.disturbances:
        ys, xs = _footprint(disturbance, n)
        lon_lo, lon_hi = float(lons[xs.min()]), float(lons[xs.max()])
        lat_lo, lat_hi = float(lats[ys.max()]), float(lats[ys.min()])
        onset = config.start + timedelta(days=12 * disturbance.from_step)
        area_ha = len(ys) * _pixel_area_ha(lons, lats)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [lon_lo, lat_hi],
                            [lon_hi, lat_hi],
                            [lon_hi, lat_lo],
                            [lon_lo, lat_lo],
                            [lon_lo, lat_hi],
                        ]
                    ],
                },
                "properties": {
                    "id": disturbance.id,
                    "schema_version": "0.1.0",
                    "date_window": {
                        "start": str(onset - timedelta(days=12)),
                        "end": str(onset),
                    },
                    "event_class": ("access-road" if disturbance.shape == "line" else "other"),
                    "status": "confirmed" if disturbance.persistent else "rejected",
                    "biome": "synthetic",
                    "evidence_source": "synthetic fixture — generated, not observed",
                    "area_ha": round(area_ha, 2),
                },
            }
        )
    return features


def _footprint(disturbance: PlantedDisturbance, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Pixel indices (ys, xs) covered by a disturbance."""
    cy = int(disturbance.center[1] * (n - 1))
    cx = int(disturbance.center[0] * (n - 1))
    half = disturbance.size_px // 2
    if disturbance.shape == "line":
        # 2-pixel-wide diagonal centered on (cy, cx)
        steps = np.arange(-half, disturbance.size_px - half)
        ys = np.clip(cy + steps, 0, n - 2)
        xs = np.clip(cx + steps, 0, n - 1)
        return np.concatenate([ys, ys + 1]), np.concatenate([xs, xs])
    # blob: square patch
    side = np.arange(-half, disturbance.size_px - half)
    yy, xx = np.meshgrid(np.clip(cy + side, 0, n - 1), np.clip(cx + side, 0, n - 1))
    return yy.ravel(), xx.ravel()


def _pixel_area_ha(lons: np.ndarray, lats: np.ndarray) -> float:
    import math

    mid_lat = math.radians(float(np.mean(lats)))
    dx_m = abs(lons[1] - lons[0]) * 111_320 * math.cos(mid_lat)
    dy_m = abs(lats[1] - lats[0]) * 110_540
    return dx_m * dy_m / 10_000


# The toy benchmark's scene: one persistent ~2 km road, one transient rain blob.
TOY_SCENE = SceneConfig(
    disturbances=[
        PlantedDisturbance(
            id="toy-road-001", shape="line", center=(0.5, 0.5), size_px=40, from_step=5
        ),
        PlantedDisturbance(
            id="toy-rain-001",
            shape="blob",
            center=(0.15, 0.75),
            size_px=10,
            coherence=0.35,
            from_step=5,
            persistent=False,
        ),
    ]
)
