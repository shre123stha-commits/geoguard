"""Monthly index stacks for the seasonal-model scan (design note §5).

For a grid and a list of months, produce per-month arrays of BUI, NDVI, a water-like mask
(Sentinel-2 median composite) and VV backscatter in dB (Sentinel-1 median composite). Each
month is cached as one .npz keyed by the grid, so re-runs and neighbouring scans over the same
area are free. Months without clear scenes yield NaN layers, never an error: the seasonal
model treats them as gaps.
"""

import hashlib
import logging
from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from app.pipeline.composite import build_optical_composite, build_radar_composite
from app.pipeline.grid import TargetGrid
from app.pipeline.optical import WATER_NIR_MAX, WATER_SWIR_MAX, compute_indices
from app.pipeline.sources.base import GridReader, ImageryError

logger = logging.getLogger(__name__)

CLOUD_MAX = 60  # per-scene; the SCL mask does the per-pixel work


@dataclass
class MonthlyStack:
    months: list[date]
    bui: np.ndarray  # (T, H, W) float32, NaN = no clear pixel
    ndvi: np.ndarray
    water: np.ndarray  # (T, H, W) bool
    vv_db: np.ndarray  # (T, H, W) float32, NaN = no radar
    n_optical: list[int]
    n_radar: list[int]

    @property
    def month_index(self) -> np.ndarray:
        m0 = self.months[0]
        return np.array([(d.year - m0.year) * 12 + (d.month - m0.month) for d in self.months])

    def optical_clear_frac(self) -> np.ndarray:
        return np.isfinite(self.bui).reshape(len(self.months), -1).mean(1)


def month_list(start: date, end: date) -> list[date]:
    y, m = start.year, start.month
    out = []
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def grid_key(grid: TargetGrid) -> str:
    t = grid.transform
    s = f"{grid.crs}|{grid.width}|{grid.height}|{t.a:.3f}|{t.e:.3f}|{t.c:.1f}|{t.f:.1f}"
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def _month_span(m: date) -> tuple[date, date]:
    return m, date(m.year, m.month, monthrange(m.year, m.month)[1])


def build_month(
    src: GridReader, grid: TargetGrid, bbox_wgs84: tuple[float, float, float, float], m: date
) -> dict[str, np.ndarray | int]:
    shape = grid.shape
    nan = np.full(shape, np.nan, np.float32)
    out: dict[str, np.ndarray | int] = {
        "bui": nan.copy(),
        "ndvi": nan.copy(),
        "water": np.zeros(shape, bool),
        "vv_db": nan.copy(),
        "n_optical": 0,
        "n_radar": 0,
    }
    span = _month_span(m)
    s2 = src.search_optical(bbox_wgs84, span, CLOUD_MAX)
    out["n_optical"] = len(s2)
    if s2:
        try:
            comp = build_optical_composite(src, s2, grid)
            red, nir, swir = comp.bands
            idx = compute_indices(red, nir, swir)
            valid = np.isfinite(idx.bui) & (comp.count > 0)
            out["bui"] = np.where(valid, idx.bui, np.nan).astype(np.float32)
            out["ndvi"] = np.where(valid, idx.ndvi, np.nan).astype(np.float32)
            out["water"] = valid & (nir < WATER_NIR_MAX) & (swir < WATER_SWIR_MAX)
        except ImageryError as exc:
            logger.warning("optical month %s skipped: %s", m, exc)
    s1 = src.search_radar(bbox_wgs84, span)
    out["n_radar"] = len(s1)
    if s1:
        try:
            rc = build_radar_composite(src, s1, grid)
            vv = rc.bands[0]
            out["vv_db"] = np.where(np.isfinite(vv) & (rc.count > 0), vv, np.nan).astype(np.float32)
        except ImageryError as exc:
            logger.warning("radar month %s skipped: %s", m, exc)
    return out


def build_stack(
    src: GridReader,
    grid: TargetGrid,
    bbox_wgs84: tuple[float, float, float, float],
    months: list[date],
    cache_dir: Path | None,
    progress: Callable[[int, int, date], None] | None = None,
) -> MonthlyStack:
    key = grid_key(grid)
    layers: list[dict[str, np.ndarray | int]] = []
    for i, m in enumerate(months):
        f = cache_dir / key / f"{m:%Y-%m}.npz" if cache_dir else None
        if f is not None and f.exists():
            with np.load(f) as z:
                layers.append({k: (int(z[k]) if k.startswith("n_") else z[k]) for k in z.files})
        else:
            lay = build_month(src, grid, bbox_wgs84, m)
            # cache only complete months (not the current month, which may still gain scenes)
            if f is not None and m < date.today().replace(day=1):
                f.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(str(f), **{k: np.asarray(v) for k, v in lay.items()})  # type: ignore[arg-type]
            layers.append(lay)
        if progress:
            progress(i + 1, len(months), m)
    return MonthlyStack(
        months=months,
        bui=np.stack([la["bui"] for la in layers]),
        ndvi=np.stack([la["ndvi"] for la in layers]),
        water=np.stack([la["water"] for la in layers]),
        vv_db=np.stack([la["vv_db"] for la in layers]),
        n_optical=[int(la["n_optical"]) for la in layers],
        n_radar=[int(la["n_radar"]) for la in layers],
    )
