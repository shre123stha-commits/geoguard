"""Common target grid for all bands (techspec §5.2 step 3, §5.3 'mismatched grids').

Every band from every scene is resampled onto this one grid before arithmetic, so a pixel
(row, col) means the same 10 m x 10 m patch of ground in S2 and S1 alike.
"""

import math
from dataclasses import dataclass

from rasterio.transform import Affine

DEFAULT_RESOLUTION_M = 10.0


@dataclass(frozen=True)
class TargetGrid:
    crs: str  # e.g. "EPSG:32644"
    transform: Affine
    width: int
    height: int
    resolution: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        left, top = self.transform.c, self.transform.f
        return left, top - self.height * self.resolution, left + self.width * self.resolution, top


def make_grid(
    bbox_utm: tuple[float, float, float, float], epsg: int, resolution: float = DEFAULT_RESOLUTION_M
) -> TargetGrid:
    """Snap a projected bbox outward to whole pixels and return a north-up grid."""
    minx, miny, maxx, maxy = bbox_utm
    if not (maxx > minx and maxy > miny):
        raise ValueError("bbox must have positive width and height")
    left = math.floor(minx / resolution) * resolution
    top = math.ceil(maxy / resolution) * resolution
    width = math.ceil((maxx - left) / resolution)
    height = math.ceil((top - miny) / resolution)
    transform = Affine(resolution, 0.0, left, 0.0, -resolution, top)
    return TargetGrid(f"EPSG:{epsg}", transform, width, height, resolution)
