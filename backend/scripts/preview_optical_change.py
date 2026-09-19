"""Task 1.6: optical change mask on the saved composites; per-parcel fractions; preview (offline).

Usage: python scripts/preview_optical_change.py ../data/samples/parcels.geojson ../data/composites
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
from app.pipeline.optical import (  # noqa: E402
    OpticalChangeParams,
    compute_indices,
    optical_change_mask,
)

log = logging.getLogger("preview_optical_change")


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

    with np.load(d / "baseline_s2.npz") as z:
        base = tuple(z["bands"])
    with np.load(d / "current_s2.npz") as z:
        cur = tuple(z["bands"])
    ib, ic = compute_indices(*base), compute_indices(*cur)

    variants = {
        "A naive defaults": OpticalChangeParams(
            center_on_median=False, exclude_water=False, opening_radius_px=0
        ),
        "B + water excl.": OpticalChangeParams(center_on_median=False, opening_radius_px=0),
        "C + centering": OpticalChangeParams(opening_radius_px=0),
        "D + 3x3 opening": OpticalChangeParams(),
    }
    masks = {}
    for f in feats:
        f["_m"] = rasterize(
            [(transform(to_utm, shape(f["geometry"])), 1)],
            out_shape=grid.shape,
            transform=grid.transform,
        ).astype(bool)
    outside = ~np.any([f["_m"] for f in feats], axis=0)
    header = (
        "".join(f"{f['properties']['name'][13:]:>14s}" for f in feats)
        + f"{'outside':>10s}{'AOI':>8s}"
    )
    log.info("candidate %% of pixels      %s", header)
    for name, p in variants.items():
        r = optical_change_mask(ib, ic, base, cur, p)
        masks[name] = r
        row = "".join(f"{100 * r.mask[f['_m']].mean():13.1f}%" for f in feats)
        log.info(
            "%-24s %s %9.1f%% %7.1f%%", name, row, 100 * r.mask[outside].mean(), 100 * r.mask.mean()
        )
    final = masks["D + 3x3 opening"]
    log.info("stats: %s", {k: round(v, 3) for k, v in final.stats.items()})
    np.savez_compressed(
        d / "optical_change.npz",
        mask=final.mask,
        d_bui=final.d_bui,
        d_ndvi=final.d_ndvi,
        water=final.water,
    )
    # Preview: 2023 false colour dimmed, candidates orange, water excluded shown blue-ish.
    red, nir, swir = cur
    fc = (
        np.dstack(
            [
                np.clip((nir - 0.05) / 0.4, 0, 1),
                np.clip((swir - 0.05) / 0.35, 0, 1),
                np.clip((red - 0.02) / 0.23, 0, 1),
            ]
        )
        * 0.45
    )
    fc[final.water] = [0.15, 0.2, 0.45]
    fc[final.mask] = [1.0, 0.45, 0.1]
    # parcel outlines
    for f in feats:
        edge = f["_m"] ^ binary_erode(f["_m"])
        fc[edge] = [0.95, 0.94, 0.9]
    _png(prev / "optical_change_mask.png", fc)
    log.info(
        "wrote %s and %s (orange = candidate, blue = excluded water, cream = parcel edge)",
        d / "optical_change.npz",
        prev / "optical_change_mask.png",
    )
    return 0


def binary_erode(m: np.ndarray) -> np.ndarray:
    from scipy.ndimage import binary_erosion

    return np.asarray(binary_erosion(m), dtype=bool)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
