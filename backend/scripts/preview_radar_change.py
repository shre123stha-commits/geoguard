"""Task 1.7: radar change mask on the saved composites; per-parcel table; preview (offline).

Usage: python scripts/preview_radar_change.py ../data/samples/parcels.geojson ../data/composites
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.radar import RadarChangeParams, radar_change_mask  # noqa: E402

log = logging.getLogger("preview_radar_change")


def _png(path: Path, rgb01: np.ndarray, scale: int = 4) -> None:
    from PIL import Image

    img = (np.nan_to_num(rgb01) * 255).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST).save(
        path
    )


def main(parcels_path: str, comp_dir: str) -> int:
    setup_logging("INFO")
    d = Path(comp_dir)
    prev = d.parent / "previews"
    feats = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    to_utm = Transformer.from_crs(4326, aoi.epsg_utm, always_xy=True).transform
    with np.load(d / "baseline_s1.npz") as z:
        base = (z["bands"][0], z["bands"][1])
    with np.load(d / "current_s1.npz") as z:
        cur = (z["bands"][0], z["bands"][1])
    with np.load(d / "optical_change.npz") as z:
        water, opt_mask = z["water"], z["mask"]

    masks = {
        f["properties"]["name"]: rasterize(
            [(transform(to_utm, shape(f["geometry"])), 1)],
            out_shape=grid.shape,
            transform=grid.transform,
        ).astype(bool)
        for f in feats
    }
    outside = ~np.any(list(masks.values()), axis=0)
    variants = {
        "A naive (no filter/centre/water)": RadarChangeParams(
            speckle_radius_px=0, center_on_median=False, opening_radius_px=0
        ),
        "B + speckle 3x3": RadarChangeParams(center_on_median=False, opening_radius_px=0),
        "C + centering": RadarChangeParams(opening_radius_px=0),
        "D + opening (final)": RadarChangeParams(),
    }
    log.info(
        "%-34s %s %9s %7s",
        "radar candidate % of pixels",
        "".join(f"{n[13:]:>14s}" for n in masks),
        "outside",
        "AOI",
    )
    res = None
    for name, p in variants.items():
        w = None if name.startswith("A") else water
        res = radar_change_mask(base, cur, water=w, params=p)
        log.info(
            "%-34s %s %8.1f%% %6.1f%%",
            name,
            "".join(f"{100 * res.mask[m].mean():13.1f}%" for m in masks.values()),
            100 * res.mask[outside].mean(),
            100 * res.mask.mean(),
        )
    assert res is not None
    log.info(
        "dSigma VV (centred) p5/p50/p95 = %.1f / %.1f / %.1f dB; raw median shift %.2f dB",
        *np.nanpercentile(res.d_sigma_vv_db, [5, 50, 95]),
        res.stats["d_vv_median_raw"],
    )
    both = res.mask & opt_mask
    log.info(
        "overlap with optical mask: radar %d px, optical %d px, both %d px (%.0f%% of optical)",
        res.mask.sum(),
        opt_mask.sum(),
        both.sum(),
        100 * both.sum() / max(opt_mask.sum(), 1),
    )
    np.savez_compressed(
        d / "radar_change.npz",
        mask=res.mask,
        d_sigma_vv_db=res.d_sigma_vv_db,
        d_sigma_vh_db=res.d_sigma_vh_db,
    )
    # Preview: current VV dB grey, radar-only orange, optical-only yellow-green, both white.
    vv = np.clip((cur[0] + 18) / 20, 0, 1) * 0.5
    img = np.dstack([vv, vv, vv])
    img[water] = [0.15, 0.2, 0.45]
    img[opt_mask] = [0.55, 0.75, 0.2]
    img[res.mask] = [1.0, 0.45, 0.1]
    img[both] = [1.0, 1.0, 1.0]
    from scipy.ndimage import binary_erosion

    for m in masks.values():
        img[m ^ binary_erosion(m)] = [0.95, 0.94, 0.9]
    _png(prev / "radar_change_mask.png", img)
    log.info(
        "wrote %s (orange = radar only, green = optical only, white = both, blue = water)",
        prev / "radar_change_mask.png",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
