"""Imagery source interface (techspec §5.1).

A *STAC catalog* is a searchable index of satellite scenes. Each scene ("item") carries a
date, footprint, cloud cover and links to its image files. Searching never downloads pixels.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Protocol

import numpy as np

BBox = tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat), EPSG:4326
DateRange = tuple[date, date]  # inclusive
Sensor = Literal["sentinel2", "sentinel1"]


@dataclass(frozen=True)
class SceneRef:
    """Provider-independent reference to one scene."""

    scene_id: str
    sensor: Sensor
    acquired_at: datetime
    cloud_cover: float | None = None  # percent, optical only
    orbit_direction: str | None = None  # radar: 'ascending' | 'descending'
    relative_orbit: int | None = None  # radar
    footprint: dict[str, Any] | None = None  # GeoJSON geometry, EPSG:4326
    assets: dict[str, str] = field(default_factory=dict)  # band key -> href (unsigned)
    meta: dict[str, Any] = field(default_factory=dict)


class ImagerySource(Protocol):
    def search_optical(self, bbox: BBox, date_range: DateRange, max_cloud: float) -> list[SceneRef]:
        """Sentinel-2 L2A scenes intersecting bbox with scene cloud cover <= max_cloud."""
        ...

    def search_radar(self, bbox: BBox, date_range: DateRange) -> list[SceneRef]:
        """Terrain-corrected Sentinel-1 scenes intersecting bbox."""
        ...

    def read_bands(
        self,
        scene: SceneRef,
        bands: list[str],
        bbox: BBox,
        out_crs: str,
        resolution: float,
    ) -> np.ndarray:
        """Windowed read of `bands` for `bbox`, resampled to a common grid (task 1.3)."""
        ...


class ImageryError(Exception):
    """Raised for provider failures and empty results with a user-readable message."""
