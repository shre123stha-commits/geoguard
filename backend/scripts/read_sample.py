"""Task 1.3: read one S2 and one S1 scene per window onto the common grid, cache, and preview.

Usage: python scripts/read_sample.py ../data/samples/parcels.geojson ../data/samples/windows.json
Writes previews to DATA_DIR/previews/. Needs internet.
"""

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.cache import RasterCache  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.sources.planetary_computer import PlanetaryComputerSource  # noqa: E402

log = logging.getLogger("read_sample")


def _stretch(a: np.ndarray, lo_p: float = 2, hi_p: float = 98) -> np.ndarray:
    lo, hi = np.nanpercentile(a, [lo_p, hi_p])
    return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)


def _save_png(path: Path, rgb01: np.ndarray) -> None:
    from PIL import Image

    img = (np.nan_to_num(rgb01) * 255).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1] * 4, img.shape[0] * 4), Image.NEAREST).save(path)


def main(parcels_path: str, windows_path: str) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    data_dir = Path(parcels_path).resolve().parents[1]  # data/
    out_dir = data_dir / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)

    parcels = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    aoi = build_aoi(parcels)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    log.info(
        "grid %s %dx%d px @ %.0f m bounds=%s",
        grid.crs,
        grid.width,
        grid.height,
        grid.resolution,
        tuple(round(b) for b in grid.bounds),
    )

    src = PlanetaryComputerSource(settings.stac_api_url, cache=RasterCache(data_dir / "cache"))
    for period in ("baseline", "current"):
        rng = (date.fromisoformat(windows[period][0]), date.fromisoformat(windows[period][1]))
        s2 = src.search_optical(aoi.bbox_wgs84, rng, settings.cloud_cover_max)
        s1 = src.search_radar(aoi.bbox_wgs84, rng)
        if not s2 or not s1:
            log.error("%s: missing scenes", period)
            return 1
        best = min(s2, key=lambda s: s.cloud_cover or 0)
        t0 = time.perf_counter()
        opt = src.read_grid(best, ["B04", "B08", "B11", "SCL"], grid)
        log.info(
            "%s S2 %s cloud=%.1f%% read in %.1fs shape=%s",
            period,
            best.acquired_at.date(),
            best.cloud_cover,
            time.perf_counter() - t0,
            opt.shape,
        )
        for name, band in zip(["B04", "B08", "B11", "SCL"], opt, strict=True):
            log.info(
                "  %s min=%.0f p50=%.0f max=%.0f nan=%.1f%%",
                name,
                np.nanmin(band),
                np.nanmedian(band),
                np.nanmax(band),
                100 * np.isnan(band).mean(),
            )
        scl = opt[3]
        classes, counts = np.unique(scl[~np.isnan(scl)].astype(int), return_counts=True)
        log.info("  SCL classes: %s", dict(zip(classes.tolist(), counts.tolist(), strict=True)))
        # False-colour preview: NIR, SWIR1, red -> vegetation red, built-up cyan/grey, water dark.
        fc = np.dstack([_stretch(opt[1]), _stretch(opt[2]), _stretch(opt[0])])
        _save_png(out_dir / f"{period}_s2_{best.acquired_at.date()}_nir_swir_red.png", fc)

        rad = s1[len(s1) // 2]
        t0 = time.perf_counter()
        sar = src.read_grid(rad, ["vv", "vh"], grid)
        vv_db = 10 * np.log10(np.where(sar[0] > 0, sar[0], np.nan))
        log.info(
            "%s S1 %s read in %.1fs vv_db p5=%.1f p50=%.1f p95=%.1f nan=%.1f%%",
            period,
            rad.acquired_at.date(),
            time.perf_counter() - t0,
            *np.nanpercentile(vv_db, [5, 50, 95]),
            100 * np.isnan(vv_db).mean(),
        )
        _save_png(
            out_dir / f"{period}_s1_{rad.acquired_at.date()}_vv_db.png",
            np.dstack([_stretch(vv_db)] * 3),
        )
    log.info("previews written to %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
