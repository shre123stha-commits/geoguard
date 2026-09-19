"""Orchestration: read every scene of a period and build S2 / S1 composites.

Not pure (does I/O through an ImagerySource) but contains no FastAPI or DB code.
"""

import logging
import time
from dataclasses import dataclass

import numpy as np

from app.pipeline.grid import TargetGrid
from app.pipeline.optical import Composite, median_composite, scl_valid_mask, to_reflectance
from app.pipeline.radar import median_composite_db
from app.pipeline.sources.base import ImageryError, SceneRef
from app.pipeline.sources.planetary_computer import PlanetaryComputerSource

logger = logging.getLogger(__name__)

S2_BANDS = ["B04", "B08", "B11"]  # red, NIR, SWIR1 (indices need exactly these)
S2_READ = [*S2_BANDS, "SCL"]
S1_BANDS = ["vv", "vh"]


@dataclass(frozen=True)
class PeriodComposites:
    optical: Composite  # bands in S2_BANDS order, reflectance [0..1]
    radar: Composite  # bands in S1_BANDS order, dB
    optical_scenes: list[SceneRef]
    radar_scenes: list[SceneRef]


def build_optical_composite(
    src: PlanetaryComputerSource, scenes: list[SceneRef], grid: TargetGrid
) -> Composite:
    if not scenes:
        raise ImageryError(
            "No clear optical scenes in that period. Try a wider window or a different season."
        )
    t0 = time.perf_counter()
    stack = np.empty((len(scenes), len(S2_BANDS), *grid.shape), dtype=np.float32)
    valid = np.empty((len(scenes), *grid.shape), dtype=bool)
    for i, scene in enumerate(scenes):
        arr = src.read_grid(scene, S2_READ, grid)
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


def build_radar_composite(
    src: PlanetaryComputerSource, scenes: list[SceneRef], grid: TargetGrid
) -> Composite:
    if not scenes:
        raise ImageryError("No radar scenes in that period. Try a wider window.")
    t0 = time.perf_counter()
    stack_lin = np.empty((len(scenes), len(S1_BANDS), *grid.shape), dtype=np.float32)
    for i, scene in enumerate(scenes):
        stack_lin[i] = src.read_grid(scene, S1_BANDS, grid)
    comp = median_composite_db(stack_lin)
    logger.info(
        "radar composite scenes=%d count_min=%d vv_db_median=%.1f in %.1fs",
        len(scenes),
        int(comp.count.min()),
        float(np.nanmedian(comp.bands[0])),
        time.perf_counter() - t0,
    )
    return comp
