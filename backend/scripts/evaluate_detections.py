"""Task 1.10: score detections against hand labels and sweep thresholds (offline).

Usage:
  python scripts/evaluate_detections.py ../data/samples/parcels.geojson ../data/composites \
      ../data/eval/labels.geojson

Prints precision per confidence class, recall, and a table for a small grid of
(T_bui, T_sar, overlap) settings. Writes data/previews/eval_sweep.csv.
"""

import json
import logging
import sys
from itertools import product
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.evaluate import Evaluation, evaluate, load_labels  # noqa: E402
from app.pipeline.fusion import FusionParams, fuse  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.optical import (  # noqa: E402
    OpticalChangeParams,
    compute_indices,
    optical_change_mask,
)
from app.pipeline.radar import RadarChangeParams, radar_change_mask  # noqa: E402
from app.pipeline.vectorize import (  # noqa: E402
    Region,
    clean_mask,
    clip_to_parcels,
    mask_to_regions,
)

log = logging.getLogger("evaluate_detections")


def run_once(
    base_s2: tuple[np.ndarray, ...],
    cur_s2: tuple[np.ndarray, ...],
    base_s1: tuple[np.ndarray, np.ndarray],
    cur_s1: tuple[np.ndarray, np.ndarray],
    feats: list[dict],  # type: ignore[type-arg]
    grid,  # type: ignore[no-untyped-def]
    t_bui: float,
    t_sar: float,
    overlap: float,
    labels,  # type: ignore[no-untyped-def]
) -> tuple[Evaluation, int]:
    ib, ic = compute_indices(*base_s2), compute_indices(*cur_s2)
    opt = optical_change_mask(ib, ic, base_s2, cur_s2, OpticalChangeParams(t_bui=t_bui))
    rad = radar_change_mask(
        base_s1, cur_s1, water=opt.water, params=RadarChangeParams(t_sar_db=t_sar)
    )
    rad_clean = clean_mask(rad.mask)
    optical = mask_to_regions(clean_mask(opt.mask), grid)
    radar = mask_to_regions(rad_clean, grid)
    fused = fuse(
        optical,
        radar,
        rad_clean,
        opt.d_bui,
        rad.d_sigma_vv_db,
        FusionParams(overlap_threshold=overlap),
    )
    dets = []
    for f in fused:
        for c in clip_to_parcels([Region(f.region.geom_utm, f.region.pixel_mask)], feats, grid):
            dets.append((c.geom_wgs84, f.confidence))
    return evaluate(dets, labels), len(dets)


def main(parcels_path: str, comp_dir: str, labels_path: str) -> int:
    setup_logging("INFO")
    d = Path(comp_dir)
    feats = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    labels = load_labels(json.loads(Path(labels_path).read_text(encoding="utf-8")))
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    with np.load(d / "baseline_s2.npz") as z:
        base_s2 = tuple(z["bands"])
    with np.load(d / "current_s2.npz") as z:
        cur_s2 = tuple(z["bands"])
    with np.load(d / "baseline_s1.npz") as z:
        base_s1 = (z["bands"][0], z["bands"][1])
    with np.load(d / "current_s1.npz") as z:
        cur_s1 = (z["bands"][0], z["bands"][1])
    n_real = sum(1 for s in labels if s.label == "real")
    log.info("labels: %d sites (%d real)", len(labels), n_real)

    # 1) current defaults
    ev, n = run_once(base_s2, cur_s2, base_s1, cur_s1, feats, grid, 0.15, 2.5, 0.3, labels)
    log.info("DEFAULTS (T_bui 0.15, T_sar 2.5, overlap 0.3): %d detections", n)
    for c in ("high", "medium", "low"):
        m = ev.per_class.get(c)
        if m:
            p = "n/a" if m.precision is None else f"{100 * m.precision:.0f}%"
            log.info("  %-6s tp=%d fp=%d unsure=%d precision=%s", c, m.tp, m.fp, m.unsure, p)
    o = ev.overall()
    log.info(
        "  all    tp=%d fp=%d unsure=%d precision=%s  recall=%.0f%% (%d/%d real sites)",
        o.tp,
        o.fp,
        o.unsure,
        "n/a" if o.precision is None else f"{100 * o.precision:.0f}%",
        100 * (ev.recall or 0),
        ev.real_matched,
        ev.real_total,
    )

    # 2) sweep
    rows = []
    log.info("SWEEP  t_bui  t_sar  overlap | n_det  high(tp/fp)  med(tp/fp)  low(tp/fp)  recall")
    for t_bui, t_sar, ov in product(
        (0.10, 0.15, 0.20, 0.25), (2.0, 2.5, 3.0, 3.5), (0.2, 0.3, 0.5)
    ):
        ev, n = run_once(base_s2, cur_s2, base_s1, cur_s1, feats, grid, t_bui, t_sar, ov, labels)
        g = {c: ev.per_class.get(c) for c in ("high", "medium", "low")}
        cell = lambda m: "  -  " if m is None else f"{m.tp}/{m.fp}"  # noqa: E731
        log.info(
            "       %.2f   %.1f    %.1f   | %4d   %8s     %8s    %8s   %4.0f%%",
            t_bui,
            t_sar,
            ov,
            n,
            cell(g["high"]),
            cell(g["medium"]),
            cell(g["low"]),
            100 * (ev.recall or 0),
        )
        rows.append(
            (
                t_bui,
                t_sar,
                ov,
                n,
                *(x for c in g.values() for x in ((c.tp, c.fp) if c else (0, 0))),
                ev.recall or 0,
            )
        )
    out = d.parent / "previews" / "eval_sweep.csv"
    out.write_text(
        "t_bui,t_sar,overlap,n_det,high_tp,high_fp,med_tp,med_fp,low_tp,low_fp,recall\n"
        + "\n".join(",".join(f"{v}" for v in r) for r in rows),
        encoding="utf-8",
    )
    log.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
