"""Orchestration: read every scene of a period and build S2 / S1 composites.

Not pure (does I/O through an ImagerySource) but contains no FastAPI or DB code.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from app.pipeline.grid import TargetGrid
from app.pipeline.optical import Composite, median_composite, scl_valid_mask, to_reflectance
from app.pipeline.radar import median_composite_db
from app.pipeline.sources.base import GridReader, ImageryError, SceneRef

logger = logging.getLogger(__name__)

S2_BANDS = ["B04", "B08", "B11"]  # red, NIR, SWIR1 (indices need exactly these)
S2_READ = [*S2_BANDS, "SCL"]
S1_BANDS = ["vv", "vh"]

# Speed (techspec §5.3 budget): scenes are read concurrently — every band of every scene is a
# separate HTTPS range read and rasterio releases the GIL while waiting — and each period is
# capped to a handful of scenes, since a median over 6 clear scenes is as stable as over 20.
READ_WORKERS = max(1, int(os.environ.get("GEOGUARD_READ_WORKERS", "8")))
MAX_OPTICAL_SCENES = max(1, int(os.environ.get("GEOGUARD_MAX_OPTICAL_SCENES", "6")))
MAX_RADAR_SCENES = max(1, int(os.environ.get("GEOGUARD_MAX_RADAR_SCENES", "8")))


def select_optical(scenes: list[SceneRef], cap: int = MAX_OPTICAL_SCENES) -> list[SceneRef]:
    """Keep the `cap` clearest scenes (lowest cloud cover), in acquisition order."""
    if len(scenes) <= cap:
        return scenes
    keep = sorted(scenes, key=lambda s: s.cloud_cover if s.cloud_cover is not None else 100)[:cap]
    return sorted(keep, key=lambda s: s.acquired_at)


def select_radar(scenes: list[SceneRef], cap: int = MAX_RADAR_SCENES) -> list[SceneRef]:
    """Keep `cap` scenes spread evenly across the period (radar has no cloud ranking)."""
    if len(scenes) <= cap:
        return scenes
    idx = np.linspace(0, len(scenes) - 1, cap).round().astype(int)
    return [scenes[i] for i in dict.fromkeys(idx.tolist())]


def read_many(
    src: GridReader, scenes: list[SceneRef], bands: list[str], grid: TargetGrid
) -> list[np.ndarray]:
    """read_grid for every scene, concurrently, results in scene order."""
    if len(scenes) == 1 or READ_WORKERS == 1:
        return [src.read_grid(s, bands, grid) for s in scenes]
    with ThreadPoolExecutor(max_workers=min(READ_WORKERS, len(scenes))) as pool:
        return list(pool.map(lambda s: src.read_grid(s, bands, grid), scenes))


@dataclass(frozen=True)
class PeriodComposites:
    optical: Composite  # bands in S2_BANDS order, reflectance [0..1]
    radar: Composite  # bands in S1_BANDS order, dB
    optical_scenes: list[SceneRef]
    radar_scenes: list[SceneRef]


def build_optical_composite(src: GridReader, scenes: list[SceneRef], grid: TargetGrid) -> Composite:
    if not scenes:
        raise ImageryError(
            "No clear optical scenes in that period. Try a wider window or a different season."
        )
    t0 = time.perf_counter()
    scenes = select_optical(scenes)
    stack = np.empty((len(scenes), len(S2_BANDS), *grid.shape), dtype=np.float32)
    valid = np.empty((len(scenes), *grid.shape), dtype=bool)
    for i, (scene, arr) in enumerate(
        zip(scenes, read_many(src, scenes, S2_READ, grid), strict=True)
    ):
        stack[i] = to_reflectance(arr[: len(S2_BANDS)], scene.meta.get("processing_baseline"))
        valid[i] = scl_valid_mask(arr[len(S2_BANDS)])
        logger.debug("scene %s valid=%.1f%%", scene.scene_id, 100 * valid[i].mean())
    comp = median_composite(stack, valid)
    logger.info(
        "optical composite scenes=%d count_min=%d count_median=%.0f nan=%.2f%% in %.1fs",
        len(scenes),
        int(comp.count.min()),
        float(np.median(comp.count)),
        100 * float(np.isnan(comp.bands[0]).mean()),
        time.perf_counter() - t0,
    )
    return comp


def build_radar_composite(src: GridReader, scenes: list[SceneRef], grid: TargetGrid) -> Composite:
    if not scenes:
        raise ImageryError("No radar scenes in that period. Try a wider window.")
    t0 = time.perf_counter()
    scenes = select_radar(scenes)
    stack_lin = np.stack(read_many(src, scenes, S1_BANDS, grid)).astype(np.float32)
    comp = median_composite_db(stack_lin)
    logger.info(
        "radar composite scenes=%d count_min=%d vv_db_median=%.1f in %.1fs",
        len(scenes),
        int(comp.count.min()),
        float(np.nanmedian(comp.bands[0])),
        time.perf_counter() - t0,
    )
    return comp
