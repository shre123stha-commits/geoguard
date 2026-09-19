"""Shared helpers for repositories: geometry (de)serialisation."""

import json
from typing import Any

import shapely
from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry


def vertex_count(g: BaseGeometry) -> int:
    return int(shapely.get_num_coordinates(g))


def geojson_to_multipolygon(geometry: dict[str, Any]) -> MultiPolygon:
    try:
        g = shape(geometry)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ValueError(f"not a GeoJSON geometry: {exc}") from exc
    if g.is_empty:
        raise ValueError("geometry is empty")
    if shapely.has_z(g):
        g = shapely.force_2d(g)
    if isinstance(g, Polygon):
        g = MultiPolygon([g])
    if not isinstance(g, MultiPolygon):
        raise ValueError(f"expected Polygon or MultiPolygon, got {g.geom_type}")
    if not g.is_valid:
        reason = shapely.is_valid_reason(g)
        raise ValueError(f"geometry is not valid ({reason})")
    minx, miny, maxx, maxy = g.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise ValueError("coordinates outside EPSG:4326 longitude/latitude range")
    return g


def to_db(g: BaseGeometry) -> WKBElement:
    return from_shape(g, srid=4326)


def from_db(elem: WKBElement | None) -> dict[str, Any] | None:
    if elem is None:
        return None
    out: dict[str, Any] = json.loads(json.dumps(mapping(to_shape(elem))))
    return out
