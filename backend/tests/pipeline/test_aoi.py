import pytest

from app.pipeline.aoi import AoiError, build_aoi, utm_epsg_for


def _square(lon: float, lat: float, half_deg: float, name: str = "p") -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon - half_deg, lat - half_deg],
                    [lon + half_deg, lat - half_deg],
                    [lon + half_deg, lat + half_deg],
                    [lon - half_deg, lat + half_deg],
                    [lon - half_deg, lat - half_deg],
                ]
            ],
        },
    }


def test_utm_zone_chennai_is_44n() -> None:
    assert utm_epsg_for(80.19, 12.94) == 32644


def test_utm_zone_southern_hemisphere() -> None:
    assert utm_epsg_for(151.2, -33.9) == 32756


def test_buffer_grows_bbox_by_about_100m() -> None:
    # ~0.001 deg ≈ 111 m square; buffered by 100 m -> ≈ 311 m per side.
    aoi = build_aoi([_square(80.19, 12.94, 0.0005)])
    w = aoi.bbox_utm[2] - aoi.bbox_utm[0]
    h = aoi.bbox_utm[3] - aoi.bbox_utm[1]
    assert 300 < w < 325 and 300 < h < 325
    assert aoi.epsg_utm == 32644
    assert aoi.bbox_wgs84[0] < 80.19 < aoi.bbox_wgs84[2]


def test_union_of_two_parcels_spans_both() -> None:
    aoi = build_aoi([_square(80.19, 12.94, 0.0005), _square(80.20, 12.95, 0.0005)])
    assert aoi.bbox_wgs84[2] > 80.20 and aoi.bbox_wgs84[1] < 12.94


def test_rejects_huge_aoi() -> None:
    with pytest.raises(AoiError, match="above"):
        build_aoi([_square(80.19, 12.94, 0.1)])  # ~22 km square ≈ 480 km2


def test_rejects_empty_and_invalid() -> None:
    with pytest.raises(AoiError):
        build_aoi([])
    bowtie = _square(80.19, 12.94, 0.001)
    ring = bowtie["geometry"]["coordinates"][0]  # type: ignore[index]
    ring[1], ring[2] = ring[2], ring[1]  # self-intersecting
    with pytest.raises(AoiError, match="invalid"):
        build_aoi([bowtie])
