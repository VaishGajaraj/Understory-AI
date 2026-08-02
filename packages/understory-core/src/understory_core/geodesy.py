"""Shared local-scale geodesy: meters per degree and pixel areas.

One place for the small-angle approximations the pipeline uses to turn
lon/lat grids into meters and hectares. Every consumer — event areas,
match distances, DEM slopes, sweep tables — reads the same constants, so
an area and the distance threshold it is scored against can never drift
apart. Good to ~0.5% at benchmark latitudes; not for precision geodesy.
"""

from __future__ import annotations

import math

import numpy as np
from pyproj import CRS

# Local length of one degree, in meters (spherical approximation).
METERS_PER_DEGREE_LAT = 110_540.0
# At the equator; scale by cos(latitude) for the local east-west length.
METERS_PER_DEGREE_LON = 111_320.0


def degree_size_meters(latitude_deg: float) -> tuple[float, float]:
    """(dy_m, dx_m): meters spanned by one degree of latitude / longitude."""
    return (
        METERS_PER_DEGREE_LAT,
        METERS_PER_DEGREE_LON * math.cos(math.radians(latitude_deg)),
    )


def pixel_area_ha(xs: np.ndarray, ys: np.ndarray, crs: str) -> float:
    """Pixel area in hectares, respecting geographic or projected grid units.

    ``xs`` and ``ys`` are the grid's coordinate vectors; spacing is read off
    the first step and, for geographic grids, scaled at the grid's mean
    latitude.
    """
    parsed = CRS.from_user_input(crs)
    if parsed.is_geographic:
        dy_per_deg, dx_per_deg = degree_size_meters(float(np.mean(ys)))
        dx_m = abs(xs[1] - xs[0]) * dx_per_deg
        dy_m = abs(ys[1] - ys[0]) * dy_per_deg
    else:
        unit_to_m = parsed.axis_info[0].unit_conversion_factor if parsed.axis_info else 1.0
        dx_m = abs(xs[1] - xs[0]) * unit_to_m
        dy_m = abs(ys[1] - ys[0]) * unit_to_m
    return dx_m * dy_m / 10_000
