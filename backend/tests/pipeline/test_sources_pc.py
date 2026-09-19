"""PlanetaryComputerSource with a mocked STAC client: no network (rules §6)."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from pystac import Asset, Item

from app.pipeline.sources.base import ImageryError
from app.pipeline.sources.planetary_computer import (
    S1_COLLECTION,
    S2_COLLECTION,
    PlanetaryComputerSource,
    _s2_scene,
)

BBOX = (80.18, 12.93, 80.20, 12.95)
RANGE = (date(2023, 1, 15), date(2023, 3, 31))
GEOM = {"type": "Polygon", "coordinates": [[[80, 12], [81, 12], [81, 13], [80, 13], [80, 12]]]}


def _item(id_: str, dt: datetime, props: dict[str, object], assets: list[str]) -> Item:
    item = Item(id=id_, geometry=GEOM, bbox=[80, 12, 81, 13], datetime=dt, properties=props)
    for a in assets:
        item.add_asset(a, Asset(href=f"https://example.invalid/{id_}/{a}.tif"))
    return item


def _source_with(items: list[Item]) -> tuple[PlanetaryComputerSource, MagicMock]:
    client = MagicMock()
    client.search.return_value.items.return_value = items
    return PlanetaryComputerSource(client=client), client


def test_search_optical_maps_fields_and_sorts_by_date() -> None:
    later = _item(
        "S2B_late",
        datetime(2023, 2, 20, tzinfo=UTC),
        {"eo:cloud_cover": 12.5, "s2:mgrs_tile": "44PMV"},
        ["B04", "B08", "B11", "SCL"],
    )
    early = _item(
        "S2A_early",
        datetime(2023, 1, 21, tzinfo=UTC),
        {"eo:cloud_cover": 3.0, "s2:mgrs_tile": "44PMV"},
        ["B04", "B08", "B11", "SCL"],
    )
    src, client = _source_with([later, early])

    scenes = src.search_optical(BBOX, RANGE, max_cloud=30)

    assert [s.scene_id for s in scenes] == ["S2A_early", "S2B_late"]
    assert scenes[0].sensor == "sentinel2" and scenes[0].cloud_cover == 3.0
    assert set(scenes[0].assets) == {"B04", "B08", "B11", "SCL"}
    kwargs = client.search.call_args.kwargs
    assert kwargs["collections"] == [S2_COLLECTION]
    assert kwargs["query"] == {"eo:cloud_cover": {"lte": 30}}
    assert kwargs["datetime"].startswith("2023-01-15/2023-03-31")


def test_search_radar_maps_orbit_fields() -> None:
    it = _item(
        "S1A_x",
        datetime(2023, 2, 1, tzinfo=UTC),
        {
            "sat:orbit_state": "descending",
            "sat:relative_orbit": 63,
            "sar:polarizations": ["VV", "VH"],
        },
        ["vv", "vh"],
    )
    src, client = _source_with([it])

    scenes = src.search_radar(BBOX, RANGE)

    assert scenes[0].sensor == "sentinel1"
    assert scenes[0].orbit_direction == "descending" and scenes[0].relative_orbit == 63
    assert client.search.call_args.kwargs["collections"] == [S1_COLLECTION]


def test_empty_result_is_empty_list_not_error() -> None:
    src, _ = _source_with([])
    assert src.search_optical(BBOX, RANGE, 30) == []


def test_reversed_range_rejected() -> None:
    src, _ = _source_with([])
    with pytest.raises(ImageryError):
        src.search_radar(BBOX, (RANGE[1], RANGE[0]))


def test_read_bands_missing_asset_raises() -> None:
    src, _ = _source_with([])
    it = _item("x", datetime(2023, 1, 1, tzinfo=UTC), {}, [])
    with pytest.raises(ImageryError, match="no asset"):
        src.read_bands(
            _s2_scene(it), ["B04"], (500_000, 1_430_000, 500_100, 1_430_100), "EPSG:32644", 10
        )


def test_reprocessed_duplicates_collapse_to_newest() -> None:
    dt = datetime(2023, 2, 14, 4, 59, 9, tzinfo=UTC)
    old = _item(
        "S2B_MSIL2A_20230214T045909_R119_T44PMV_20230214T135437",
        dt,
        {"eo:cloud_cover": 6.6, "s2:mgrs_tile": "44PMV"},
        ["B04"],
    )
    new = _item(
        "S2B_MSIL2A_20230214T045909_R119_T44PMV_20240816T064335",
        dt,
        {"eo:cloud_cover": 6.6, "s2:mgrs_tile": "44PMV"},
        ["B04"],
    )
    src, _ = _source_with([old, new])

    scenes = src.search_optical(BBOX, RANGE, 30)

    assert len(scenes) == 1
    assert scenes[0].scene_id.endswith("20240816T064335")
