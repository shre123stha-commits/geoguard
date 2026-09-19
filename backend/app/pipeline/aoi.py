"""AOI helpers (techspec §5.2 step 1). Pure functions: GeoJSON/shapely in, numbers out."""

from dataclasses import dataclass
from typing import Any

from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from app.pipeline.sources.base import BBox

AOI_BUFFER_M = 100.0
MAX_AOI_KM2 = 100.0


class AoiError(ValueError):
    """AOI cannot be built (empty, invalid, or too large)."""


@dataclass(frozen=True)
class Aoi:
    bbox_wgs84: BBox
    epsg_utm: int
    bbox_utm: tuple[float, float, float, float]
    area_km2: float


def utm_epsg_for(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing (lon, lat). Chennai (80.2E, 12.9N) -> 32644."""
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def parcels_union(features: list[dict[str, Any]]) -> BaseGeometry:
    geoms = [shape(f["geometry"]) for f in features]
    if not geoms:
        raise AoiError("no parcels given")
    for f, g in zip(features, geoms, strict=True):
        if not g.is_valid:
            raise AoiError(f"invalid geometry in parcel {f.get('properties', {}).get('name')}")
    return unary_union(geoms)


def build_aoi(features: list[dict[str, Any]], buffer_m: float = AOI_BUFFER_M) -> Aoi:
    """Union of parcels, buffered in metres in the local UTM zone, returned in both CRSs."""
    union = parcels_union(features)
    c = union.centroid
    epsg = utm_epsg_for(c.x, c.y)
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    to_wgs = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    buffered_utm = transform(to_utm, union).buffer(buffer_m).envelope
    area_km2 = buffered_utm.area / 1e6
    if area_km2 > MAX_AOI_KM2:
        raise AoiError(f"AOI is {area_km2:.0f} km2, above the {MAX_AOI_KM2:.0f} km2 limit")
    minx, miny, maxx, maxy = transform(to_wgs, buffered_utm).bounds
    bu = buffered_utm.bounds
    return Aoi(
        bbox_wgs84=(minx, miny, maxx, maxy),
        epsg_utm=epsg,
        bbox_utm=(bu[0], bu[1], bu[2], bu[3]),
        area_km2=area_km2,
    )
