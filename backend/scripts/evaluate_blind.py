# ruff: noqa: N803, N806, E501, T201
"""Blind labelling protocol, step 2: score every method against the blind cell labels.

Usage:
  python scripts/evaluate_blind.py ../data/eval/blind_cells ../data/samples/parcels.geojson \
      ../data/composites ../data/phenology [../docs/figures]

Positive = cell labelled `new_built`; negative = `no_change` or `other_change`; `cannot_tell`
is excluded. A method "flags" a cell when its change mask covers at least 2 Sentinel-2 pixels of it (8 % of a
50 m cell). Reports precision, recall and F1 with 95 % Wilson intervals, and writes blind_results.csv.

Methods scored (all from the same data, so the comparison is fair):
  * v1 fused (high+medium+low), v1 fused high+medium, v1 optical only, v1 radar only
    — from the two-window composites (baseline Jan–Mar 2020, current Jan–Mar 2023)
  * two-window optical on the monthly stack (same season)
  * phenology-normalised (defaults), and with 3-month persistence
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ablation import Data, Variant, run_masks  # noqa: E402
from phenology_change import load_stack, two_window, water_monthly  # noqa: E402

from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.phenology import PhenologyParams, detect  # noqa: E402
from app.pipeline.vectorize import clean_mask  # noqa: E402

MIN_PX = 2


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k: int, n: int) -> str:
    if n == 0:
        return "   n/a          "
    lo, hi = wilson(k, n)
    return f"{100 * k / n:5.1f}% [{100 * lo:4.1f}–{100 * hi:5.1f}] ({k}/{n})"


def main(
    cells_dir: str, parcels: str, comp_dir: str, stack_dir: str, out_dir: str | None = None
) -> int:
    cells_dir_p = Path(cells_dir)
    cells = json.loads((cells_dir_p / "cells.geojson").read_text(encoding="utf-8"))["features"]
    labels: dict[str, str] = {}
    with (cells_dir_p / "sheet.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            labels[r["id"]] = (r["label"] or "").strip()
    usable = {c["id"]: labels.get(c["id"], "") for c in cells}
    pos = {k for k, v in usable.items() if v == "new_built"}
    neg = {k for k, v in usable.items() if v in ("no_change", "other_change")}
    skipped = [k for k, v in usable.items() if v not in ("new_built", "no_change", "other_change")]
    if not pos and not neg:
        print("sheet.csv has no labels yet — fill it in first (see README.txt).")
        return 1
    print(
        f"cells: {len(cells)}  positive: {len(pos)}  negative: {len(neg)}  excluded/unlabelled: {len(skipped)}"
    )

    feats = json.loads(Path(parcels).read_text(encoding="utf-8"))["features"]
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    to_utm = Transformer.from_crs(4326, aoi.epsg_utm, always_xy=True).transform
    cell_masks = {
        c["id"]: rasterize(
            [(shp_transform(to_utm, shape(c["geometry"])), 1)],
            out_shape=grid.shape,
            transform=grid.transform,
        ).astype(bool)
        for c in cells
    }

    masks: dict[str, np.ndarray] = {}
    if Path(comp_dir, "baseline_s2.npz").exists():
        D = Data(parcels, comp_dir, str(cells_dir_p / "cells.geojson"))
        masks["v1 fused, all classes"] = run_masks(Variant("f", "f"), D)
        masks["v1 fused, high + medium"] = run_masks(
            Variant("f", "f", classes=("high", "medium")), D
        )
        masks["v1 optical only"] = run_masks(Variant("o", "o", radar=False, fuse_=False), D)
        masks["v1 radar only"] = run_masks(Variant("r", "r", optical=False, fuse_=False), D)
    if list(Path(stack_dir).glob("????-??.npz")):
        S = load_stack(Path(stack_dir))
        T = len(S.months)
        masks["two-window optical, same season (stack)"] = two_window(
            S, S.window((2020, 1), (2020, 3)), S.window((2023, 1), (2023, 3))
        )
        ref = np.array([d.year <= 2020 for d in S.months])
        water = water_monthly(S)
        for name, p in {
            "phenology (defaults)": PhenologyParams(),
            "phenology (3-month persistence)": PhenologyParams(persist=3),
        }.items():
            ch, _, _ = detect(S.bui, S.ndvi, np.arange(T), ref, p, water=water)
            masks[name] = clean_mask(ch.mask)

    rows = []
    print(f"\n{'method':44s} {'precision':32s} {'recall':32s} F1")
    for name, m in masks.items():
        flagged = {cid for cid, cm in cell_masks.items() if (m & cm).sum() >= MIN_PX}
        tp = len(flagged & pos)
        fp = len(flagged & neg)
        fn = len(pos - flagged)
        P = tp / (tp + fp) if tp + fp else float("nan")
        R = tp / (tp + fn) if tp + fn else float("nan")
        F = 2 * P * R / (P + R) if P + R and not math.isnan(P + R) else float("nan")
        print(f"{name:44s} {fmt(tp, tp + fp)} {fmt(tp, tp + fn)} {100 * F:5.1f}")
        rows.append(
            {
                "method": name,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": P,
                "recall": R,
                "f1": F,
                "p_lo": wilson(tp, tp + fp)[0],
                "p_hi": wilson(tp, tp + fp)[1],
                "r_lo": wilson(tp, tp + fn)[0],
                "r_hi": wilson(tp, tp + fn)[1],
            }
        )
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        with Path(out_dir, "blind_results.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {Path(out_dir, 'blind_results.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
