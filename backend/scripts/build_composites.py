"""Task 1.4: build cloud-free median composites per period and write previews.

Usage: python scripts/build_composites.py PARCELS.geojson WINDOWS.json  (paths under data/samples/)
Outputs: data/composites/{period}_s2.npz, {period}_s1.npz and PNGs in data/previews/.
First run needs internet (reads every scene); later runs are served from data/cache/.
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
from app.pipeline.composite import build_optical_composite, build_radar_composite  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.sources.base import ImageryError  # noqa: E402
from app.pipeline.sources.planetary_computer import PlanetaryComputerSource  # noqa: E402

log = logging.getLogger("build_composites")


def _stretch(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((a - lo) / (hi - lo), 0, 1)


def _png(path: Path, rgb01: np.ndarray, scale: int = 4) -> None:
    from PIL import Image

    img = (np.nan_to_num(rgb01) * 255).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST).save(
        path
    )


def main(parcels_path: str, windows_path: str) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    data_dir = Path(parcels_path).resolve().parents[1]
    prev, comp_dir = data_dir / "previews", data_dir / "composites"
    prev.mkdir(exist_ok=True)
    comp_dir.mkdir(exist_ok=True)

    parcels = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    aoi = build_aoi(parcels)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    src = PlanetaryComputerSource(settings.stac_api_url, cache=RasterCache(data_dir / "cache"))

    for period in ("baseline", "current"):
        rng = (date.fromisoformat(windows[period][0]), date.fromisoformat(windows[period][1]))
        t0 = time.perf_counter()
        try:
            s2 = src.search_optical(aoi.bbox_wgs84, rng, settings.cloud_cover_max)
            s1 = src.search_radar(aoi.bbox_wgs84, rng)
            opt = build_optical_composite(src, s2, grid)
            rad = build_radar_composite(src, s1, grid)
        except ImageryError as exc:
            log.error("%s: %s", period, exc)
            return 2
        red, nir, swir = opt.bands
        log.info(
            "%s composite in %.0fs: B04 p50=%.3f B08 p50=%.3f B11 p50=%.3f | valid count "
            "min=%d p50=%.0f max=%d | pixels with <3 obs: %d",
            period,
            time.perf_counter() - t0,
            np.nanmedian(red),
            np.nanmedian(nir),
            np.nanmedian(swir),
            opt.count.min(),
            np.median(opt.count),
            opt.count.max(),
            int((opt.count < 3).sum()),
        )
        vv_db, vh_db = rad.bands
        log.info(
            "%s radar: VV dB p5/p50/p95 = %.1f/%.1f/%.1f  VH p50 = %.1f",
            period,
            *np.nanpercentile(vv_db, [5, 50, 95]),
            np.nanmedian(vh_db),
        )
        np.savez_compressed(
            comp_dir / f"{period}_s2.npz",
            bands=opt.bands,
            count=opt.count,
            scene_ids=np.array([s.scene_id for s in s2]),
        )
        np.savez_compressed(
            comp_dir / f"{period}_s1.npz",
            bands=rad.bands,
            count=rad.count,
            scene_ids=np.array([s.scene_id for s in s1]),
        )
        # Previews: false colour (NIR, SWIR, red), valid-count heat, VV dB.
        _png(
            prev / f"{period}_composite_s2_nir_swir_red.png",
            np.dstack(
                [_stretch(nir, 0.05, 0.45), _stretch(swir, 0.05, 0.40), _stretch(red, 0.02, 0.25)]
            ),
        )
        cnt = _stretch(opt.count.astype(np.float32), 0, float(opt.n_scenes))
        _png(prev / f"{period}_composite_valid_count.png", np.dstack([cnt, cnt, cnt]))
        vv = _stretch(vv_db, -18, 2)
        _png(prev / f"{period}_composite_s1_vv_db.png", np.dstack([vv, vv, vv]))
    log.info("composites -> %s, previews -> %s", comp_dir, prev)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
