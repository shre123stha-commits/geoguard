# ruff: noqa: N803, N806, E501
"""Ablation study for the design note (docs/design-contribution.md §4).

Usage:
  python scripts/ablation.py ../data/samples/parcels.geojson ../data/composites \
      ../data/eval/labels.geojson ../docs/figures

Runs the same labelled Pallikaranai set through variants of the v1 detector, each with one
design element removed, and writes:
  * ablation.csv     — per-variant detections, tp / fp / unsure, precision, recall
  * ablation.png     — bar chart of precision and recall per variant
  * pr_curve.png     — precision–recall points over the ΔBUI threshold, optical-only vs fused

Labels: 7 real sites (incl. one known miss), 2 unsure; any detection that matches no
labelled site counts as a false positive (conservative — see design note §6 on label bias).
"""

import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

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

log = logging.getLogger("ablation")

CREAM = "#f3efe6"
DARK = "#0d0b09"


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    optical: bool = True
    radar: bool = True
    fuse_: bool = True  # False → every optical (or radar) region is a detection on its own
    t_bui: float = 0.15
    t_sar: float = 2.5
    overlap: float = 0.3
    center: bool = True
    water: bool = True
    opening: int = 1
    min_area: float = 400.0
    classes: tuple[str, ...] = ("high", "medium", "low")  # classes counted as "alerts"


VARIANTS = [
    Variant("fusion", "Full method (optical + radar fusion)"),
    Variant("fusion_hm", "Full method, high + medium only", classes=("high", "medium")),
    Variant("optical_only", "Optical only (ΔBUI ∧ ΔNDVI)", radar=False, fuse_=False),
    Variant("radar_only", "Radar only (Δσ°VV)", optical=False, fuse_=False),
    Variant("no_water", "− water exclusion", water=False),
    Variant("no_center", "− AOI-median centring", center=False),
    Variant("no_opening", "− 3×3 opening", opening=0),
    Variant("no_minarea", "− 400 m² minimum (100 m²)", min_area=100.0),
]


class Data:
    def __init__(self, parcels: str, comp_dir: str, labels: str) -> None:
        d = Path(comp_dir)
        self.feats = json.loads(Path(parcels).read_text(encoding="utf-8"))["features"]
        self.labels = load_labels(json.loads(Path(labels).read_text(encoding="utf-8")))
        aoi = build_aoi(self.feats)
        self.grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
        with np.load(d / "baseline_s2.npz") as z:
            self.base_s2 = tuple(z["bands"])
        with np.load(d / "current_s2.npz") as z:
            self.cur_s2 = tuple(z["bands"])
        with np.load(d / "baseline_s1.npz") as z:
            self.base_s1 = (z["bands"][0], z["bands"][1])
        with np.load(d / "current_s1.npz") as z:
            self.cur_s1 = (z["bands"][0], z["bands"][1])


def run(v: Variant, D: Data) -> tuple[Evaluation, int]:
    ib, ic = compute_indices(*D.base_s2), compute_indices(*D.cur_s2)
    opt = optical_change_mask(
        ib,
        ic,
        D.base_s2,
        D.cur_s2,
        OpticalChangeParams(
            t_bui=v.t_bui,
            center_on_median=v.center,
            exclude_water=v.water,
            opening_radius_px=v.opening,
        ),
    )
    water = opt.water if v.water else np.zeros(opt.mask.shape, bool)
    rad = radar_change_mask(
        D.base_s1,
        D.cur_s1,
        water=water,
        params=RadarChangeParams(
            t_sar_db=v.t_sar, center_on_median=v.center, opening_radius_px=v.opening
        ),
    )
    rad_clean = clean_mask(rad.mask, v.opening) if v.opening else rad.mask
    opt_clean = clean_mask(opt.mask, v.opening) if v.opening else opt.mask
    optical = mask_to_regions(opt_clean, D.grid) if v.optical else []
    radar = mask_to_regions(rad_clean, D.grid) if v.radar else []
    dets: list[tuple[object, str]] = []
    if v.fuse_:
        fused = fuse(
            optical,
            radar,
            rad_clean,
            opt.d_bui,
            rad.d_sigma_vv_db,
            FusionParams(overlap_threshold=v.overlap),
        )
        for f in fused:
            if f.confidence not in v.classes:
                continue
            for c in clip_to_parcels(
                [Region(f.region.geom_utm, f.region.pixel_mask)], D.feats, D.grid, v.min_area
            ):
                dets.append((c.geom_wgs84, f.confidence))
    else:
        regions = optical if v.optical else radar
        label = "optical" if v.optical else "radar"
        for r in regions:
            for c in clip_to_parcels([r], D.feats, D.grid, v.min_area):
                dets.append((c.geom_wgs84, label))
    ev = evaluate(dets, D.labels)  # type: ignore[arg-type]
    return ev, len(dets)


def summarize(ev: Evaluation, classes: tuple[str, ...]) -> dict[str, float | int | None]:
    o = ev.overall(classes)
    return {
        "tp": o.tp,
        "fp": o.fp,
        "unsure": o.unsure,
        "precision": o.precision,
        "recall": ev.recall,
    }


def style(ax: plt.Axes) -> None:
    ax.set_facecolor(DARK)
    for s in ax.spines.values():
        s.set_color(CREAM)
        s.set_alpha(0.3)
    ax.tick_params(colors=CREAM, labelsize=9)
    ax.yaxis.label.set_color(CREAM)
    ax.xaxis.label.set_color(CREAM)
    ax.title.set_color(CREAM)
    ax.grid(axis="y", color=CREAM, alpha=0.12, linewidth=0.6)


def main(parcels: str, comp_dir: str, labels: str, out_dir: str) -> int:
    setup_logging("WARNING")
    log.setLevel(logging.INFO)
    D = Data(parcels, comp_dir, labels)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for v in VARIANTS:
        ev, n = run(v, D)
        classes = v.classes if v.fuse_ else (("optical",) if v.optical else ("radar",))
        s = summarize(ev, classes)
        rows.append({"variant": v.key, "label": v.label, "n_det": n, **s})
        log.info(
            "%-38s n=%2d tp=%d fp=%d unsure=%d P=%s R=%s",
            v.label,
            n,
            s["tp"],
            s["fp"],
            s["unsure"],
            "n/a" if s["precision"] is None else f"{100 * s['precision']:.0f}%",  # type: ignore[operator]
            "n/a" if s["recall"] is None else f"{100 * s['recall']:.0f}%",  # type: ignore[operator]
        )
    with (out / "ablation.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # --- figure 1: horizontal bars ---
    fig, ax = plt.subplots(figsize=(8.5, 4.6), facecolor=DARK)
    style(ax)
    ax.grid(axis="x", color=CREAM, alpha=0.12, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    y = np.arange(len(rows))[::-1]
    P = [100 * (r["precision"] or 0) for r in rows]
    R = [100 * (r["recall"] or 0) for r in rows]
    ax.barh(y + 0.2, P, 0.38, color=CREAM, alpha=0.9, label="precision")
    ax.barh(y - 0.2, R, 0.38, color=CREAM, alpha=0.4, label="recall")
    for i, r in enumerate(rows):
        ax.text(P[i] + 1, y[i] + 0.2, f"{P[i]:.0f}", va="center", color=CREAM, fontsize=8)
        ax.text(R[i] + 1, y[i] - 0.2, f"{R[i]:.0f}", va="center", color=CREAM, fontsize=8)
        ax.text(118, y[i], f"n = {r['n_det']}", va="center", color=CREAM, fontsize=8, alpha=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels([r["label"] for r in rows], fontsize=9)
    ax.set_xlim(0, 128)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("%")
    ax.set_title("Ablation on the Pallikaranai labelled set (7 real sites, 2 unsure)", fontsize=10)
    leg = ax.legend(frameon=False, fontsize=8, loc="lower right")
    for t in leg.get_texts():
        t.set_color(CREAM)
    fig.tight_layout()
    fig.savefig(out / "ablation.png", dpi=170, facecolor=DARK)

    # --- figure 2: PR over ΔBUI threshold ---
    ts = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30]
    curves = {
        "optical only": [
            summarize(run(Variant("o", "o", radar=False, fuse_=False, t_bui=t), D)[0], ("optical",))
            for t in ts
        ],
        "fused, all classes": [
            summarize(run(Variant("f", "f", t_bui=t), D)[0], ("high", "medium", "low")) for t in ts
        ],
        "fused, high + medium": [
            summarize(
                run(Variant("f", "f", t_bui=t, classes=("high", "medium")), D)[0],
                ("high", "medium"),
            )
            for t in ts
        ],
    }
    fig, ax = plt.subplots(figsize=(5.2, 4.4), facecolor=DARK)
    style(ax)
    ax.grid(axis="x", color=CREAM, alpha=0.12, linewidth=0.6)
    markers = {"optical only": "o", "fused, all classes": "s", "fused, high + medium": "^"}
    alphas = {"optical only": 0.45, "fused, all classes": 0.8, "fused, high + medium": 1.0}
    for name, pts in curves.items():
        rr = [100 * (p["recall"] or 0) for p in pts]
        pp = [100 * (p["precision"] or 0) for p in pts]
        ax.plot(
            rr, pp, marker=markers[name], color=CREAM, alpha=alphas[name], lw=1, ms=5, label=name
        )
        for t, r_, p_ in zip(ts, rr, pp, strict=True):
            if t in (0.05, 0.15, 0.30):
                ax.annotate(
                    f"{t:.2f}",
                    (r_, p_),
                    textcoords="offset points",
                    xytext=(4, 4),
                    color=CREAM,
                    fontsize=7,
                    alpha=0.8,
                )
    ax.set_xlabel("recall (%)")
    ax.set_ylabel("precision (%)")
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 105)
    ax.set_title("Precision–recall over the ΔBUI threshold", fontsize=10)
    leg = ax.legend(frameon=False, fontsize=8, loc="lower left")
    for t in leg.get_texts():
        t.set_color(CREAM)
    fig.tight_layout()
    fig.savefig(out / "pr_curve.png", dpi=170, facecolor=DARK)
    with (out / "pr_curve.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["series", "t_bui", "tp", "fp", "unsure", "precision", "recall"])
        for name, pts in curves.items():
            for t, p in zip(ts, pts, strict=True):
                w.writerow([name, t, p["tp"], p["fp"], p["unsure"], p["precision"], p["recall"]])
    log.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
