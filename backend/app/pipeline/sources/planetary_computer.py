"""Microsoft Planetary Computer STAC source (free, anonymous; see tracker §6)."""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import numpy as np
import planetary_computer
from pystac import Item
from pystac_client import Client
from pystac_client.exceptions import APIError

from app.pipeline.sources.base import BBox, DateRange, ImageryError, SceneRef

logger = logging.getLogger(__name__)

DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = "sentinel-2-l2a"
S1_COLLECTION = "sentinel-1-rtc"
# Assets we will read in task 1.3 (S2: red, NIR, SWIR1, scene classification; S1: VV, VH).
S2_ASSETS = ("B04", "B08", "B11", "SCL", "visual")
S1_ASSETS = ("vv", "vh")
_MAX_ITEMS = 200


class PlanetaryComputerSource:
    def __init__(self, stac_url: str = "", *, client: Client | None = None) -> None:
        self._url = stac_url or DEFAULT_STAC_URL
        self._client = client

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = Client.open(self._url, modifier=planetary_computer.sign_inplace)
        return self._client

    def search_optical(self, bbox: BBox, date_range: DateRange, max_cloud: float) -> list[SceneRef]:
        items = self._search(
            S2_COLLECTION, bbox, date_range, query={"eo:cloud_cover": {"lte": max_cloud}}
        )
        scenes = _dedupe_reprocessed([_s2_scene(i) for i in items])
        logger.info(
            "s2 search bbox=%s range=%s..%s max_cloud=%s -> %d scenes",
            bbox,
            date_range[0],
            date_range[1],
            max_cloud,
            len(scenes),
        )
        return sorted(scenes, key=lambda s: s.acquired_at)

    def search_radar(self, bbox: BBox, date_range: DateRange) -> list[SceneRef]:
        items = self._search(S1_COLLECTION, bbox, date_range)
        scenes = [_s1_scene(i) for i in items]
        logger.info(
            "s1 search bbox=%s range=%s..%s -> %d scenes",
            bbox,
            date_range[0],
            date_range[1],
            len(scenes),
        )
        return sorted(scenes, key=lambda s: s.acquired_at)

    def read_bands(
        self, scene: SceneRef, bands: list[str], bbox: BBox, out_crs: str, resolution: float
    ) -> np.ndarray:
        raise NotImplementedError("windowed reads arrive in task 1.3")

    def _search(
        self,
        collection: str,
        bbox: BBox,
        date_range: DateRange,
        query: dict[str, Any] | None = None,
    ) -> list[Item]:
        start, end = date_range
        if start > end:
            raise ImageryError(f"date range start {start} is after end {end}")
        try:
            search = self.client.search(
                collections=[collection],
                bbox=list(bbox),
                datetime=f"{start.isoformat()}/{end.isoformat()}T23:59:59Z",
                query=query,
                max_items=_MAX_ITEMS,
            )
            return list(search.items())
        except APIError as exc:
            raise ImageryError(f"STAC search failed for {collection}: {exc}") from exc


def _dedupe_reprocessed(scenes: list[SceneRef]) -> list[SceneRef]:
    """Keep one scene per (tile, acquisition time).

    ESA reprocesses Sentinel-2 archives (e.g. the 2024 Collection-1 reprocessing), so a catalog
    can hold two items for one overpass. Keep the newest processing (last token in the id).
    """
    best: dict[tuple[object, datetime], SceneRef] = {}
    for s in scenes:
        key = (s.meta.get("tile"), s.acquired_at)
        if key not in best or s.scene_id.rsplit("_", 1)[-1] > best[key].scene_id.rsplit("_", 1)[-1]:
            best[key] = s
    return list(best.values())


def _acquired(item: Item) -> datetime:
    dt = item.datetime or item.properties.get("start_datetime")
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    raise ImageryError(f"scene {item.id} has no datetime")


def _hrefs(item: Item, keys: Iterable[str]) -> dict[str, str]:
    return {k: item.assets[k].href for k in keys if k in item.assets}


def _s2_scene(item: Item) -> SceneRef:
    p = item.properties
    return SceneRef(
        scene_id=item.id,
        sensor="sentinel2",
        acquired_at=_acquired(item),
        cloud_cover=p.get("eo:cloud_cover"),
        footprint=item.geometry,
        assets=_hrefs(item, S2_ASSETS),
        meta={
            "tile": p.get("s2:mgrs_tile"),
            "platform": p.get("platform"),
            "nodata_pct": p.get("s2:nodata_pixel_percentage"),
        },
    )


def _s1_scene(item: Item) -> SceneRef:
    p = item.properties
    return SceneRef(
        scene_id=item.id,
        sensor="sentinel1",
        acquired_at=_acquired(item),
        orbit_direction=p.get("sat:orbit_state"),
        relative_orbit=p.get("sat:relative_orbit"),
        footprint=item.geometry,
        assets=_hrefs(item, S1_ASSETS),
        meta={"platform": p.get("platform"), "polarizations": p.get("sar:polarizations")},
    )
