"""Offline imagery source (techspec §5.1 `LocalFolderSource`): scenes stored as GeoTIFFs.

Layout (root = `DATA_DIR/local_scenes` by default):

    root/
      scenes.json               manifest: list of scene records (see `write_manifest`)
      <scene_id>/<band>.tif     one single-band GeoTIFF per band, any CRS/resolution

Used by the offline pipeline tests and by installations without internet access. Files are
read with rasterio and resampled onto the target grid exactly like the online source.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject
from shapely.geometry import box, mapping

from app.pipeline.grid import TargetGrid
from app.pipeline.sources.base import BBox, DateRange, ImageryError, SceneRef

logger = logging.getLogger(__name__)
MANIFEST = "scenes.json"
_NEAREST_BANDS = {"SCL"}


class LocalFolderSource:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._scenes: list[SceneRef] | None = None

    # ---- manifest -------------------------------------------------------------------------
    def scenes(self) -> list[SceneRef]:
        if self._scenes is None:
            p = self.root / MANIFEST
            if not p.exists():
                raise ImageryError(f"No local scenes: {p} not found")
            raw = json.loads(p.read_text(encoding="utf-8"))
            self._scenes = [self._to_ref(r) for r in raw]
        return self._scenes

    def _to_ref(self, r: dict[str, Any]) -> SceneRef:
        folder = self.root / r["scene_id"]
        assets = {b: str(folder / f"{b}.tif") for b in r.get("bands", [])}
        return SceneRef(
            scene_id=r["scene_id"],
            sensor=r["sensor"],
            acquired_at=datetime.fromisoformat(r["acquired_at"]),
            cloud_cover=r.get("cloud_cover"),
            orbit_direction=r.get("orbit_direction"),
            relative_orbit=r.get("relative_orbit"),
            footprint=r.get("footprint"),
            assets=assets,
            meta=r.get("meta", {}),
        )

    def _filter(self, sensor: str, bbox: BBox, date_range: DateRange) -> list[SceneRef]:
        want = box(*bbox)
        out = []
        for s in self.scenes():
            if s.sensor != sensor:
                continue
            d = s.acquired_at.date()
            if not (date_range[0] <= d <= date_range[1]):
                continue
            if s.footprint is not None:
                from shapely.geometry import shape

                if not shape(s.footprint).intersects(want):
                    continue
            out.append(s)
        return sorted(out, key=lambda s: s.acquired_at)

    def search_optical(self, bbox: BBox, date_range: DateRange, max_cloud: float) -> list[SceneRef]:
        return [
            s
            for s in self._filter("sentinel2", bbox, date_range)
            if s.cloud_cover is None or s.cloud_cover <= max_cloud
        ]

    def search_radar(self, bbox: BBox, date_range: DateRange) -> list[SceneRef]:
        return self._filter("sentinel1", bbox, date_range)

    # ---- pixels ---------------------------------------------------------------------------
    def read_bands(
        self, scene: SceneRef, bands: list[str], bbox: BBox, out_crs: str, resolution: float
    ) -> np.ndarray:
        from app.pipeline.grid import make_grid

        return self.read_grid(scene, bands, make_grid(bbox, int(out_crs.split(":")[1]), resolution))

    def read_grid(self, scene: SceneRef, bands: list[str], grid: TargetGrid) -> np.ndarray:
        out = np.full((len(bands), grid.height, grid.width), np.nan, dtype=np.float32)
        for i, band in enumerate(bands):
            href = scene.assets.get(band)
            if href is None or not Path(href).exists():
                raise ImageryError(f"local scene {scene.scene_id} has no file for band '{band}'")
            resampling = Resampling.nearest if band in _NEAREST_BANDS else Resampling.bilinear
            with rasterio.open(href) as src:
                reproject(
                    source=rasterio.band(src, 1),
                    destination=out[i],
                    dst_transform=grid.transform,
                    dst_crs=grid.crs,
                    dst_nodata=np.nan,
                    src_nodata=src.nodata,
                    resampling=resampling,
                )
            if band == "SCL":
                out[i][out[i] == 0] = np.nan
        return out


# ---- writing fixtures ----------------------------------------------------------------------


def write_scene(
    root: Path,
    scene_id: str,
    sensor: str,
    acquired_at: datetime,
    bands: dict[str, np.ndarray],
    grid: TargetGrid,
    cloud_cover: float | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one scene's bands as GeoTIFFs on `grid`; returns its manifest record."""
    folder = root / scene_id
    folder.mkdir(parents=True, exist_ok=True)
    for name, arr in bands.items():
        if arr.shape != grid.shape:
            raise ValueError(f"band {name} shape {arr.shape} != grid {grid.shape}")
        with rasterio.open(
            folder / f"{name}.tif",
            "w",
            driver="GTiff",
            height=grid.height,
            width=grid.width,
            count=1,
            dtype="float32",
            crs=grid.crs,
            transform=Affine(*grid.transform[:6]),
            nodata=np.nan,
            compress="deflate",
        ) as dst:
            dst.write(np.asarray(arr, dtype=np.float32), 1)
    from pyproj import Transformer
    from shapely.ops import transform as shp_transform

    to_wgs = Transformer.from_crs(grid.crs, 4326, always_xy=True).transform
    footprint = mapping(shp_transform(to_wgs, box(*grid.bounds)))
    return {
        "scene_id": scene_id,
        "sensor": sensor,
        "acquired_at": acquired_at.isoformat(),
        "cloud_cover": cloud_cover,
        "bands": sorted(bands),
        "footprint": footprint,
        "meta": meta or {},
    }


def write_manifest(root: Path, records: list[dict[str, Any]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / MANIFEST
    p.write_text(json.dumps(records, indent=1), encoding="utf-8")
    return p
