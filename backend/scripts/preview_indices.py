"""Task 1.5: compute NDVI/NDBI/BUI on the saved composites and write previews (offline).

Usage: python scripts/preview_indices.py ../data/composites
"""

import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.optical import compute_indices  # noqa: E402

log = logging.getLogger("preview_indices")


def _png(path: Path, rgb01: np.ndarray, scale: int = 4) -> None:
    from PIL import Image

    img = (np.nan_to_num(rgb01) * 255).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST).save(
        path
    )


def _gray(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    g = np.clip((a - lo) / (hi - lo), 0, 1)
    return np.dstack([g, g, g])


def _diverging(d: np.ndarray, lim: float) -> np.ndarray:
    """Negative -> blue, zero -> dark, positive -> orange (labelled in the log, not colour-only)."""
    x = np.clip(d / lim, -1, 1)
    r = np.clip(x, 0, 1)
    b = np.clip(-x, 0, 1)
    return np.dstack([r, 0.4 * r, b])


def main(comp_dir: str) -> int:
    setup_logging("INFO")
    d = Path(comp_dir)
    prev = d.parent / "previews"
    idx = {}
    for period in ("baseline", "current"):
        with np.load(d / f"{period}_s2.npz") as z:
            red, nir, swir = z["bands"]
        idx[period] = compute_indices(red, nir, swir)
        for name in ("ndvi", "ndbi", "bui"):
            a = getattr(idx[period], name)
            log.info(
                "%s %s p5/p50/p95 = %.2f / %.2f / %.2f",
                period,
                name.upper(),
                *np.nanpercentile(a, [5, 50, 95]),
            )
        _png(prev / f"{period}_ndvi.png", _gray(idx[period].ndvi, -0.2, 0.8))
        _png(prev / f"{period}_bui.png", _gray(idx[period].bui, -1.2, 0.4))
    d_bui = idx["current"].bui - idx["baseline"].bui
    d_ndvi = idx["current"].ndvi - idx["baseline"].ndvi
    log.info(
        "dBUI (current-baseline) p5/p50/p95 = %.2f / %.2f / %.2f; pixels > +0.15: %d (%.1f%%)",
        *np.nanpercentile(d_bui, [5, 50, 95]),
        int((d_bui > 0.15).sum()),
        100 * float((d_bui > 0.15).mean()),
    )
    log.info("dNDVI p5/p50/p95 = %.2f / %.2f / %.2f", *np.nanpercentile(d_ndvi, [5, 50, 95]))
    _png(prev / "d_bui.png", _diverging(d_bui, 0.5))
    np.savez_compressed(
        d / "indices.npz",
        d_bui=d_bui,
        d_ndvi=d_ndvi,
        **{f"{p}_{n}": getattr(idx[p], n) for p in idx for n in ("ndvi", "ndbi", "bui")},
    )
    log.info(
        "wrote %s and previews to %s (d_bui.png: orange = BUI rose, blue = BUI fell)",
        d / "indices.npz",
        prev,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "../data/composites"))
