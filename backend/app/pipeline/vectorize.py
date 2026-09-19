"""Raster mask -> cleaned polygons -> clipped to parcels with geodesic area (techspec §5.2 10-11).

Pure: arrays + shapely geometries in, dataclasses out. No DB (PostGIS ST_Intersection is used
later by the service layer; here we do the same with shapely so Phase 1 runs standalone).
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from pyproj import Geod, Transformer
from rasterio.features import shapes
from scipy.ndimage import binary_closing, binary_opening
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from app.pipeline.grid import TargetGrid

MIN_AREA_M2_DEFAULT = 400.0
SIMPLIFY_M_DEFAULT = 5.0
_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class Region:
    """One candidate region in the grid CRS (metres)."""

    geom_utm: BaseGeometry
    pixel_mask: np.ndarray  # bool (H, W) of this region's pixels, for per-region statistics


@dataclass(frozen=True)
class ClippedRegion:
    parcel_index: int
    parcel_name: str
    geom_utm: BaseGeometry  # intersection with the parcel, metres
    geom_wgs84: MultiPolygon  # for storage (EPSG:4326)
    area_m2: float  # geodesic
    overlap_area_m2: float  # same as area_m2 in v1 (clip keeps only the intersecting part)
    pixel_mask: np.ndarray


def clean_mask(mask: np.ndarray, radius_px: int = 1) -> np.ndarray:
    """Closing then opening with a (2r+1)^2 window: fills 1-px gaps, removes 1-px specks."""
    if radius_px <= 0:
        return mask.astype(bool)
    k = np.ones((2 * radius_px + 1,) * 2, dtype=bool)
    out = binary_closing(mask.astype(bool), structure=k)
    return np.asarray(binary_opening(out, structure=k), dtype=bool)


def mask_to_regions(
    mask: np.ndarray,
    grid: TargetGrid,
    min_area_m2: float = MIN_AREA_M2_DEFAULT,
    simplify_m: float = SIMPLIFY_M_DEFAULT,
) -> list[Region]:
    """Connected True pixels -> polygons in grid CRS; drop those below min_area_m2 (projected)."""
    if mask.shape != grid.shape:
        raise ValueError("mask shape does not match grid")
    m = mask.astype(np.uint8)
    regions: list[Region] = []
    for geom_json, value in shapes(
        m, mask=m.astype(bool), transform=grid.transform, connectivity=8
    ):
        if value != 1:
            continue
        poly = shape(geom_json)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.area < min_area_m2:
            continue
        simplified = poly.simplify(simplify_m, preserve_topology=True)
        if simplified.is_empty or not simplified.is_valid:
            simplified = poly
        # pixel mask for this region: rasterize the *unsimplified* polygon back onto the grid
        from rasterio.features import rasterize

        pm = rasterize([(poly, 1)], out_shape=grid.shape, transform=grid.transform).astype(bool)
        regions.append(Region(geom_utm=simplified, pixel_mask=pm))
    return regions


def geodesic_area_m2(geom_wgs84: BaseGeometry) -> float:
    """Ellipsoidal area in m² of a (Multi)Polygon in EPSG:4326."""
    area, _ = _GEOD.geometry_area_perimeter(geom_wgs84)
    return abs(float(area))


def _to_multi(g: BaseGeometry) -> MultiPolygon:
    if isinstance(g, MultiPolygon):
        return g
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    polys = [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon) and not p.is_empty]
    return MultiPolygon(polys)


def clip_to_parcels(
    regions: list[Region],
    parcels: list[dict[str, Any]],
    grid: TargetGrid,
    min_area_m2: float = MIN_AREA_M2_DEFAULT,
) -> list[ClippedRegion]:
    """Intersect each region with each parcel; keep intersecting parts >= min_area_m2.

    parcels: GeoJSON features in EPSG:4326 (as in data/samples/parcels.geojson).
    Regions outside every parcel are discarded (v1 rule). A region straddling two parcels
    yields one ClippedRegion per parcel.
    """
    epsg = int(grid.crs.split(":")[1])
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    to_wgs = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    parcels_utm = [transform(to_utm, shape(p["geometry"])) for p in parcels]
    out: list[ClippedRegion] = []
    for r in regions:
        for i, (p_utm, feat) in enumerate(zip(parcels_utm, parcels, strict=True)):
            if not r.geom_utm.intersects(p_utm):
                continue
            inter = r.geom_utm.intersection(p_utm)
            inter = unary_union(
                [g for g in getattr(inter, "geoms", [inter]) if isinstance(g, Polygon)]
            )
            if inter.is_empty or inter.area < min_area_m2:
                continue
            wgs = _to_multi(transform(to_wgs, inter))
            area = geodesic_area_m2(wgs)
            out.append(
                ClippedRegion(
                    parcel_index=i,
                    parcel_name=str(feat.get("properties", {}).get("name", i)),
                    geom_utm=inter,
                    geom_wgs84=wgs,
                    area_m2=area,
                    overlap_area_m2=area,
                    pixel_mask=r.pixel_mask,
                )
            )
    return out


def to_feature(c: ClippedRegion, props: dict[str, Any] | None = None) -> dict[str, Any]:
    p: dict[str, Any] = {
        "parcel": c.parcel_name,
        "area_m2": round(c.area_m2, 1),
        "overlap_area_m2": round(c.overlap_area_m2, 1),
    }
    if props:
        p.update(props)
    return {"type": "Feature", "properties": p, "geometry": mapping(c.geom_wgs84)}
