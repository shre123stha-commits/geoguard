"""Microsoft Planetary Computer STAC source (free, anonymous; see tracker §6)."""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import numpy as np
import planetary_computer
import rasterio
from pystac import Item
from pystac_client import Client
from pystac_client.exceptions import APIError
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.warp import reproject

from app.pipeline.cache import RasterCache
from app.pipeline.grid import TargetGrid
from app.pipeline.sources.base import BBox, DateRange, ImageryError, SceneRef

logger = logging.getLogger(__name__)

DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = "sentinel-2-l2a"
S1_COLLECTION = "sentinel-1-rtc"
# Assets we will read in task 1.3 (S2: red, NIR, SWIR1, scene classification; S1: VV, VH).
S2_ASSETS = ("B04", "B08", "B11", "SCL", "visual")
S1_ASSETS = ("vv", "vh")
_MAX_ITEMS = 200
# Categorical or integer-coded bands must never be interpolated.
_NEAREST_BANDS = {"SCL"}
# GDAL env: read only the byte ranges needed from the COGs, never whole files.
_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
}


class PlanetaryComputerSource:
    def __init__(
        self, stac_url: str = "", *, client: Client | None = None, cache: RasterCache | None = None
    ) -> None:
        self._url = stac_url or DEFAULT_STAC_URL
        self._client = client
        self._cache = cache

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
        """Protocol form: bbox is a projected bbox in `out_crs`. Delegates to `read_grid`."""
        from app.pipeline.grid import make_grid

        epsg = int(out_crs.split(":")[1])
        return self.read_grid(scene, bands, make_grid(bbox, epsg, resolution))

    def read_grid(self, scene: SceneRef, bands: list[str], grid: TargetGrid) -> np.ndarray:
        """Read `bands` of one scene resampled onto `grid`.

        Returns float32 array (len(bands), H, W); nodata -> NaN. Units are the provider's:
        S2 L2A = scaled reflectance integers (0..10000, offset handled in 1.4), SCL = class codes,
        S1 RTC = linear power (gamma0), NOT dB.
        """
        key = (
            self._cache.key(scene.scene_id, bands, grid.crs, grid.bounds, grid.resolution)
            if self._cache
            else None
        )
        if self._cache and key:
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        out = np.full((len(bands), grid.height, grid.width), np.nan, dtype=np.float32)
        with rasterio.Env(**_GDAL_ENV):
            for i, band in enumerate(bands):
                href = scene.assets.get(band)
                if href is None:
                    raise ImageryError(f"scene {scene.scene_id} has no asset '{band}'")
                out[i] = _read_one(self._signed(href), band, grid)
        if self._cache and key:
            self._cache.put(key, out)
        logger.info(
            "read %s bands=%s grid=%dx%d nan=%.1f%%",
            scene.scene_id,
            bands,
            grid.height,
            grid.width,
            100 * float(np.isnan(out).mean()),
        )
        return out

    def _signed(self, href: str) -> str:
        # Anonymous SAS signing; the STAC client already signs search results in place, but
        # SceneRefs may be rebuilt from stored hrefs, so sign again (idempotent).
        return str(planetary_computer.sign(href))

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
            # Processing baseline >= 04.00 (Jan 2022) stores reflectance with a +1000 offset
            # (BOA_ADD_OFFSET). Task 1.4 must subtract it before computing indices.
            "processing_baseline": p.get("s2:processing_baseline"),
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


def _read_one(href: str, band: str, grid: TargetGrid) -> np.ndarray:
    resampling = Resampling.nearest if band in _NEAREST_BANDS else Resampling.bilinear
    dst = np.full(grid.shape, np.nan, dtype=np.float32)
    try:
        with rasterio.open(href) as src:
            # reproject() computes the source window itself and reads only that region.
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=np.nan,
                src_nodata=src.nodata,
                resampling=resampling,
            )
    except RasterioIOError as exc:
        raise ImageryError(f"could not read {band} for {href.split('?')[0]}: {exc}") from exc
    if band == "SCL":
        dst[dst == 0] = np.nan  # SCL 0 = no data
    return dst
