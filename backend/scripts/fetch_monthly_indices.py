# ruff: noqa: N803, N806, E501
"""Build a monthly NDVI/BUI stack for the evaluation AOI from Planetary Computer (free, anonymous).

Usage:
  python scripts/fetch_monthly_indices.py ../data/samples/parcels.geojson ../data/phenology 2019-01 2023-12

One .npz per month: ndvi, bui, nir, swir (float32, NaN where no clear pixel), valid (bool),
n_scenes.
Used by scripts/phenology_change.py (design note §B). Idempotent: existing months are skipped.
"""

import json
import logging
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.composite import build_optical_composite  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.optical import compute_indices  # noqa: E402
from app.pipeline.sources.base import ImageryError  # noqa: E402
from app.services.scan_runner import default_source_factory  # noqa: E402

log = logging.getLogger("fetch_monthly")
CLOUD_MAX = 60


def months(a: str, b: str) -> list[date]:
    y, m = (int(x) for x in a.split("-"))
    y2, m2 = (int(x) for x in b.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def main(parcels: str, out_dir: str, start: str, end: str) -> int:
    setup_logging("WARNING")
    logging.getLogger("fetch_monthly").setLevel(logging.INFO)
    feats = json.loads(Path(parcels).read_text(encoding="utf-8"))["features"]
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "grid.json").write_text(
        json.dumps(
            {
                "epsg": aoi.epsg_utm,
                "shape": list(grid.shape),
                "transform": list(grid.transform)[:6],
                "bbox_wgs84": list(aoi.bbox_wgs84),
            }
        ),
        encoding="utf-8",
    )
    src = default_source_factory(get_settings())
    for m in months(start, end):
        f = out / f"{m:%Y-%m}.npz"
        if f.exists():
            continue
        last = monthrange(m.year, m.month)[1]
        scenes = src.search_optical(aoi.bbox_wgs84, (m, date(m.year, m.month, last)), CLOUD_MAX)
        if not scenes:
            np.savez_compressed(
                f,
                ndvi=np.full(grid.shape, np.nan, np.float32),
                bui=np.full(grid.shape, np.nan, np.float32),
                valid=np.zeros(grid.shape, bool),
                n_scenes=0,
            )
            log.info("%s: no scenes", m)
            continue
        try:
            comp = build_optical_composite(src, scenes, grid)
        except ImageryError as exc:
            log.warning("%s: %s", m, exc)
            continue
        idx = compute_indices(*comp.bands)
        valid = np.isfinite(idx.bui) & (comp.count > 0)
        np.savez_compressed(
            f,
            ndvi=np.where(valid, idx.ndvi, np.nan).astype(np.float32),
            bui=np.where(valid, idx.bui, np.nan).astype(np.float32),
            nir=np.where(valid, comp.bands[1], np.nan).astype(np.float32),
            swir=np.where(valid, comp.bands[2], np.nan).astype(np.float32),
            valid=valid,
            n_scenes=len(scenes),
        )
        log.info("%s: %d scenes, %.0f%% clear", m, len(scenes), 100 * valid.mean())
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
