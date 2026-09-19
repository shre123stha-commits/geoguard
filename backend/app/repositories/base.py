"""Shared helpers for repositories: geometry (de)serialisation."""

import json
from typing import Any

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry


def geojson_to_multipolygon(geometry: dict[str, Any]) -> MultiPolygon:
    g = shape(geometry)
    if isinstance(g, Polygon):
        g = MultiPolygon([g])
    if not isinstance(g, MultiPolygon):
        raise ValueError(f"expected Polygon or MultiPolygon, got {g.geom_type}")
    if not g.is_valid:
        raise ValueError("geometry is not valid (self-intersection or bad ring)")
    return g


def to_db(g: BaseGeometry) -> WKBElement:
    return from_shape(g, srid=4326)


def from_db(elem: WKBElement | None) -> dict[str, Any] | None:
    if elem is None:
        return None
    out: dict[str, Any] = json.loads(json.dumps(mapping(to_shape(elem))))
    return out
