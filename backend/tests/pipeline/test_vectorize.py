"""SYNTHETIC masks on a 10 m grid at UTM 44N with hand-checkable areas."""

import numpy as np
import pytest
from shapely.geometry import box, mapping

from app.pipeline.grid import make_grid
from app.pipeline.vectorize import (
    clean_mask,
    clip_to_parcels,
    geodesic_area_m2,
    mask_to_regions,
    to_feature,
)

EPSG = 32644
# 20x20 px grid: x 500000..500200, y 1430000..1430200 (row 0 = top = y 1430200)
GRID = make_grid((500_000, 1_430_000, 500_200, 1_430_200), EPSG, 10)


def _parcel(minx: float, miny: float, maxx: float, maxy: float, name: str) -> dict[str, object]:
    from pyproj import Transformer
    from shapely.ops import transform

    to_wgs = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    return {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": mapping(transform(to_wgs, box(minx, miny, maxx, maxy))),
    }


def test_square_block_becomes_one_polygon_with_exact_area() -> None:
    m = np.zeros(GRID.shape, bool)
    m[2:8, 3:9] = True  # 6x6 px = 3600 m2
    regs = mask_to_regions(m, GRID, simplify_m=0)
    assert len(regs) == 1
    assert regs[0].geom_utm.area == pytest.approx(3600.0)
    assert regs[0].pixel_mask.sum() == 36
    minx, miny, maxx, maxy = regs[0].geom_utm.bounds
    assert (minx, maxx) == (500_030, 500_090) and (miny, maxy) == (1_430_120, 1_430_180)


def test_sub_min_area_speck_dropped_and_large_kept() -> None:
    m = np.zeros(GRID.shape, bool)
    m[1, 1] = True  # 100 m2 < 400
    m[1:3, 5:7] = True  # 400 m2 exactly -> kept
    m[10:14, 10:14] = True  # 1600 m2
    regs = mask_to_regions(m, GRID)
    assert sorted(round(r.geom_utm.area) for r in regs) == [400, 1600]


def test_clean_mask_fills_gap_and_removes_speck() -> None:
    m = np.zeros((10, 10), bool)
    m[2:8, 2:8] = True
    m[5, 5] = False  # hole
    m[0, 9] = True  # speck
    c = clean_mask(m)
    assert c[5, 5] and not c[0, 9] and c.sum() == 36


def test_clip_splits_region_across_two_parcels_and_drops_outside() -> None:
    m = np.zeros(GRID.shape, bool)
    m[5:10, 5:15] = True  # 50x100 m block, x 500050..500150
    regs = mask_to_regions(m, GRID, simplify_m=0)
    parcels = [
        _parcel(500_000, 1_430_000, 500_100, 1_430_200, "west"),  # covers x<500100
        _parcel(500_100, 1_430_000, 500_130, 1_430_200, "mid"),  # x 500100..500130
        _parcel(500_180, 1_430_000, 500_200, 1_430_200, "far"),  # no overlap
    ]
    clipped = clip_to_parcels(regs, parcels, GRID)
    by = {c.parcel_name: c for c in clipped}
    assert set(by) == {"west", "mid"}
    assert by["west"].geom_utm.area == pytest.approx(50 * 50)
    assert by["mid"].geom_utm.area == pytest.approx(50 * 30)
    # geodesic area agrees with projected area to well under 1 % at this latitude
    assert by["west"].area_m2 == pytest.approx(2500, rel=0.01)
    f = to_feature(by["mid"], {"confidence": "medium"})
    assert f["geometry"]["type"] == "MultiPolygon" and f["properties"]["confidence"] == "medium"


def test_geodesic_area_of_known_square() -> None:
    # ~1 km square near the equator: 0.009 deg ≈ 1000 m at lat 0.
    sq = box(80.0, 0.0, 80.009, 0.009)
    a = geodesic_area_m2(sq)
    assert a == pytest.approx(1.0e6, rel=0.01)
