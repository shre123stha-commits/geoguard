"""Evidence thumbnails per detection (techspec §5.2 step 12, task 4.4).

Three PNGs under `DATA_DIR/evidence/<scan_id>/<detection_id>/`:
  before_rgb  – baseline false-colour composite (SWIR, NIR, red) cropped around the detection
  after_rgb   – same for the current period
  change_map  – dBUI heat map (grey = no change, bright = stronger built-up signal)

Sentinel-2 at 10 m is coarse, so crops are upscaled (nearest) to stay legible. Paths stored in
the DB are relative to DATA_DIR and never built from user input.
"""

import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform as shp_transform

from app.pipeline.composite import PeriodComposites
from app.pipeline.grid import TargetGrid

logger = logging.getLogger(__name__)

MARGIN_M = 60.0
MIN_CROP_M = 200.0
UPSCALE = 6
# Reflectance stretch for the false-colour view (percentiles are unstable on tiny crops).
STRETCH = {"swir": (0.03, 0.45), "nir": (0.05, 0.55), "red": (0.02, 0.30)}

EvidenceRecord = tuple[str, str, tuple[int, int], dict[str, Any]]  # kind, rel path, (w,h), bounds


def _stretch(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out: np.ndarray = np.clip((np.nan_to_num(a, nan=lo) - lo) / (hi - lo), 0.0, 1.0)
    return out


def false_colour(bands: np.ndarray) -> np.ndarray:
    """(3,H,W) red/NIR/SWIR reflectance -> (H,W,3) uint8 in SWIR-NIR-red order."""
    red, nir, swir = bands
    rgb = np.dstack(
        [
            _stretch(swir, *STRETCH["swir"]),
            _stretch(nir, *STRETCH["nir"]),
            _stretch(red, *STRETCH["red"]),
        ]
    )
    return (rgb * 255).astype(np.uint8)


def change_heat(d_bui: np.ndarray, lo: float = 0.0, hi: float = 0.6) -> np.ndarray:
    """dBUI -> (H,W,3) uint8: neutral grey for <= lo, warm ramp up to hi."""
    v = _stretch(d_bui, lo, hi)
    grey = np.full(v.shape, 0.25)
    r = grey + v * (0.91 - 0.25)
    g = grey + v * (0.45 - 0.25)
    b = grey + v * (0.35 - 0.25)
    return (np.dstack([r, g, b]) * 255).astype(np.uint8)


def crop_window(
    bounds_utm: tuple[float, float, float, float], grid: TargetGrid
) -> tuple[slice, slice, tuple[float, float, float, float]]:
    """Pixel slices covering bounds + margin (at least MIN_CROP_M square), clamped to grid."""
    minx, miny, maxx, maxy = bounds_utm
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    half = max((maxx - minx) / 2, (maxy - miny) / 2, MIN_CROP_M / 2) + MARGIN_M
    res = grid.resolution
    left, top = grid.transform.c, grid.transform.f
    c0 = max(0, int((cx - half - left) // res))
    c1 = min(grid.width, int(np.ceil((cx + half - left) / res)))
    r0 = max(0, int((top - (cy + half)) // res))
    r1 = min(grid.height, int(np.ceil((top - (cy - half)) / res)))
    crop_bounds = (left + c0 * res, top - r1 * res, left + c1 * res, top - r0 * res)
    return slice(r0, r1), slice(c0, c1), crop_bounds


class EvidenceWriter:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def write_all(
        self,
        scan_id: uuid.UUID,
        detection_id: uuid.UUID,
        bounds_utm: tuple[float, float, float, float],
        grid: TargetGrid,
        base: PeriodComposites,
        cur: PeriodComposites,
        d_bui: np.ndarray,
    ) -> list[EvidenceRecord]:
        rows, cols, crop_bounds = crop_window(bounds_utm, grid)
        if rows.stop - rows.start < 2 or cols.stop - cols.start < 2:
            return []
        to_wgs = Transformer.from_crs(grid.crs, 4326, always_xy=True).transform
        bounds_wgs: dict[str, Any] = dict(mapping(shp_transform(to_wgs, box(*crop_bounds))))
        folder = self.root / str(scan_id) / str(detection_id)
        folder.mkdir(parents=True, exist_ok=True)
        images = {
            "before_rgb": false_colour(base.optical.bands[:, rows, cols]),
            "after_rgb": false_colour(cur.optical.bands[:, rows, cols]),
            "change_map": change_heat(d_bui[rows, cols]),
        }
        out: list[EvidenceRecord] = []
        for kind, arr in images.items():
            img = Image.fromarray(arr).resize(
                (arr.shape[1] * UPSCALE, arr.shape[0] * UPSCALE), Image.Resampling.NEAREST
            )
            path = folder / f"{kind}.png"
            img.save(path, optimize=True)
            rel = path.relative_to(self.root.parent).as_posix()
            out.append((kind, rel, img.size, bounds_wgs))
        return out
