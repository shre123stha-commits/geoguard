# ruff: noqa: N803, N806, E501
"""Experiment for the design note §5: two-window change detection vs phenology-normalised
change detection on the same 60-month Sentinel-2 stack (scripts/fetch_monthly_indices.py).

Usage:
  python scripts/phenology_change.py ../data/samples/parcels.geojson ../data/phenology \
      ../data/eval/labels.geojson ../docs/figures

Writes phenology_results.csv, onsets.csv, seasonal_cycle.png, site_anomalies.png.
Optical only on both sides (radar is not part of this comparison).
"""

import csv
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib
import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.evaluate import evaluate, load_labels  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.optical import WATER_NIR_MAX, WATER_SWIR_MAX  # noqa: E402
from app.pipeline.phenology import PhenologyParams, detect  # noqa: E402
from app.pipeline.vectorize import clean_mask, clip_to_parcels, mask_to_regions  # noqa: E402

log = logging.getLogger("phenology")
CREAM, DARK = "#f3efe6", "#0d0b09"


@dataclass
class Stack:
    months: list[date]
    bui: np.ndarray
    ndvi: np.ndarray
    nir: np.ndarray
    swir: np.ndarray

    def idx(self, y: int, m: int) -> int:
        return self.months.index(date(y, m, 1))

    def window(self, a: tuple[int, int], b: tuple[int, int]) -> slice:
        return slice(self.idx(*a), self.idx(*b) + 1)


def load_stack(d: Path) -> Stack:
    files = sorted(d.glob("????-??.npz"))
    months = [date(int(f.stem[:4]), int(f.stem[5:]), 1) for f in files]
    arrs = {k: [] for k in ("bui", "ndvi", "nir", "swir")}
    for f in files:
        with np.load(f) as z:
            for k in arrs:
                arrs[k].append(z[k] if k in z else np.full(z["bui"].shape, np.nan, np.float32))
    return Stack(months, *(np.stack(arrs[k]) for k in ("bui", "ndvi", "nir", "swir")))


def water_mask(S: Stack, sl: slice) -> np.ndarray:
    nir = np.nanmedian(S.nir[sl], 0)
    swir = np.nanmedian(S.swir[sl], 0)
    return (nir < WATER_NIR_MAX) & (swir < WATER_SWIR_MAX)


def water_monthly(S: Stack) -> np.ndarray:
    """(T, H, W) water-like per month; also true in the month after (drying pond)."""
    w = (S.nir < WATER_NIR_MAX) & (S.swir < WATER_SWIR_MAX)
    w[1:] |= w[:-1]
    return w


def two_window(
    S: Stack, base: slice, cur: slice, t_bui: float = 0.15, t_ndvi: float = 0.10
) -> np.ndarray:
    """v1 optical rule on window medians (centred, water excluded, 3×3 opening)."""
    d_bui = np.nanmedian(S.bui[cur], 0) - np.nanmedian(S.bui[base], 0)
    d_ndvi = np.nanmedian(S.ndvi[cur], 0) - np.nanmedian(S.ndvi[base], 0)
    d_bui -= np.nanmedian(d_bui)
    d_ndvi -= np.nanmedian(d_ndvi)
    water = water_mask(S, base) | water_mask(S, cur)
    m = (d_bui >= t_bui) & (-d_ndvi >= t_ndvi) & ~water & np.isfinite(d_bui)
    return clean_mask(m)


def score(mask: np.ndarray, label: str, feats, grid, labels):  # type: ignore[no-untyped-def]
    regions = mask_to_regions(mask, grid)
    dets = []
    for r in regions:
        for c in clip_to_parcels([r], feats, grid):
            dets.append((c.geom_wgs84, label))
    ev = evaluate(dets, labels)
    o = ev.overall((label,))
    return {
        "n_det": len(dets),
        "tp": o.tp,
        "fp": o.fp,
        "unsure": o.unsure,
        "precision": o.precision,
        "recall": ev.recall,
    }, regions


def site_masks(labels_fc: dict, grid, epsg: int) -> list[tuple[int, str, np.ndarray]]:  # type: ignore[no-untyped-def,type-arg]
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    out = []
    for f in labels_fc["features"]:
        g = shp_transform(to_utm, shape(f["geometry"]))
        m = rasterize([(g, 1)], out_shape=grid.shape, transform=grid.transform).astype(bool)
        out.append((f["properties"]["id"], f["properties"]["label"], m))
    return out


def style(ax):  # type: ignore[no-untyped-def]
    ax.set_facecolor(DARK)
    for s in ax.spines.values():
        s.set_color(CREAM)
        s.set_alpha(0.3)
    ax.tick_params(colors=CREAM, labelsize=8)
    for lab in (ax.yaxis.label, ax.xaxis.label, ax.title):
        lab.set_color(CREAM)
    ax.grid(color=CREAM, alpha=0.1, linewidth=0.6)


def main(parcels: str, stack_dir: str, labels_path: str, out_dir: str) -> int:
    setup_logging("WARNING")
    log.setLevel(logging.INFO)
    feats = json.loads(Path(parcels).read_text(encoding="utf-8"))["features"]
    labels_fc = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    labels = load_labels(labels_fc)
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    S = load_stack(Path(stack_dir))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    T = len(S.months)
    mi = np.arange(T)
    parcel_mask = rasterize(
        [
            (
                shp_transform(
                    Transformer.from_crs(4326, aoi.epsg_utm, always_xy=True).transform,
                    shape(f["geometry"]),
                ),
                1,
            )
            for f in feats
        ],
        out_shape=grid.shape,
        transform=grid.transform,
    ).astype(bool)

    results = []

    # --- E1/E2: two-window, same season vs mismatched seasons ---
    windows = {
        "two-window, same season (Jan–Mar 2020 → Jan–Mar 2023)": (
            ((2020, 1), (2020, 3)),
            ((2023, 1), (2023, 3)),
        ),
        "two-window, wet → dry (Sep–Nov 2019 → Mar–May 2023)": (
            ((2019, 9), (2019, 11)),
            ((2023, 3), (2023, 5)),
        ),
        "two-window, dry → wet (Mar–May 2020 → Sep–Nov 2023)": (
            ((2020, 3), (2020, 5)),
            ((2023, 9), (2023, 11)),
        ),
    }
    for name, (b, c) in windows.items():
        m = two_window(S, S.window(*b), S.window(*c)) & parcel_mask
        r, _ = score(m, "optical", feats, grid, labels)
        results.append({"method": name, **r})

    # --- E3: phenology-normalised; reference 2019–2020, test 2021–2023 ---
    ref = np.array([d.year <= 2020 for d in S.months])
    water = water_monthly(S)
    for pname, params in {
        "phenology-normalised (T 0.15, 2 months)": PhenologyParams(),
        "phenology-normalised (T 0.15, 1 month)": PhenologyParams(persist=1),
        "phenology-normalised (T 0.15, 3 months)": PhenologyParams(persist=3),
    }.items():
        ch, mb, mn = detect(S.bui, S.ndvi, mi, ref, params, water=water)
        m = clean_mask(ch.mask) & parcel_mask
        r, regions = score(m, "phenology", feats, grid, labels)
        results.append({"method": pname, **r})
        if params.persist == 2:
            change, model_b = ch, mb
            # Same test as E2 but for the phenology method: evaluate only what it had flagged
            # by the end of the "wrong-season" current windows.
            for tag, (yy, mm) in {"by May 2023": (2023, 5), "by Nov 2023": (2023, 11)}.items():
                upto = (change.onset_index >= 0) & (change.onset_index <= S.idx(yy, mm))
                r2, _ = score(clean_mask(upto) & parcel_mask, "phenology", feats, grid, labels)
                results.append({"method": f"phenology-normalised, onsets {tag}", **r2})

    for r in results:
        log.info(
            "%-62s n=%2d tp=%d fp=%d unsure=%d P=%s R=%s",
            r["method"],
            r["n_det"],
            r["tp"],
            r["fp"],
            r["unsure"],
            "n/a" if r["precision"] is None else f"{100 * r['precision']:.0f}%",
            "n/a" if r["recall"] is None else f"{100 * r['recall']:.0f}%",
        )
    with (out / "phenology_results.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    # --- onsets per labelled site ---
    sites = site_masks(labels_fc, grid, aoi.epsg_utm)
    onsets = []
    for sid, lab, sm in sites:
        px = change.onset_index[sm]
        flagged = px[px >= 0]
        onset = S.months[int(np.median(flagged))] if flagged.size else None
        frac = flagged.size / max(1, sm.sum())
        onsets.append((sid, lab, onset, round(frac, 2)))
        log.info("site %d (%s): onset %s, %.0f%% of pixels", sid, lab, onset, 100 * frac)
    with (out / "onsets.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["site", "label", "onset_month", "flagged_pixel_fraction"])
        w.writerows([(a, b, c.isoformat()[:7] if c else "", d) for a, b, c, d in onsets])

    # --- figure: seasonal cycle of the AOI with harmonic fit ---
    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor=DARK)
    style(ax)
    ctrl = next(f for f in feats if "Control-Marsh" in f["properties"]["name"])
    cm = rasterize(
        [
            (
                shp_transform(
                    Transformer.from_crs(4326, aoi.epsg_utm, always_xy=True).transform,
                    shape(ctrl["geometry"]),
                ),
                1,
            )
        ],
        out_shape=grid.shape,
        transform=grid.transform,
    ).astype(bool)
    obs = np.array(
        [
            np.nanmean(S.bui[t][cm]) if np.isfinite(S.bui[t][cm]).mean() > 0.2 else np.nan
            for t in range(T)
        ]
    )
    pred = np.array([np.nanmean(model_b.predict(np.array([t]))[0][cm]) for t in range(T)])
    x = np.arange(T)
    ax.plot(x, obs, "o", color=CREAM, ms=3.5, label="observed monthly BUI, control marsh")
    ax.plot(
        x, pred, "-", color=CREAM, alpha=0.6, lw=1.2, label="two-harmonic fit (2019–2020 reference)"
    )
    ax.axvspan(-0.5, S.idx(2020, 12) + 0.5, color=CREAM, alpha=0.05)
    ax.text(
        1,
        ax.get_ylim()[1] if False else np.nanmax(obs) + 0.02,
        "reference period",
        color=CREAM,
        fontsize=8,
        alpha=0.8,
    )
    ax.axhline(np.nanmedian(obs), color=CREAM, alpha=0.25, lw=0.8)
    ax.annotate(
        "",
        xy=(S.idx(2019, 5), obs[S.idx(2019, 5)]),
        xytext=(S.idx(2019, 5), obs[S.idx(2019, 9)]),
        arrowprops={"arrowstyle": "<->", "color": CREAM, "alpha": 0.8},
    )
    ax.text(
        S.idx(2019, 5) + 0.7,
        (obs[S.idx(2019, 5)] + obs[S.idx(2019, 9)]) / 2,
        f"seasonal swing\n{obs[S.idx(2019, 5)] - obs[S.idx(2019, 9)]:.2f} ≈ {(obs[S.idx(2019, 5)] - obs[S.idx(2019, 9)]) / 0.15:.1f}× the 0.15\nchange threshold",
        color=CREAM,
        fontsize=7.5,
        va="center",
    )
    ticks = [t for t, d in enumerate(S.months) if d.month == 1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(S.months[t].year) for t in ticks])
    ax.set_ylabel("BUI = NDBI − NDVI")
    ax.set_title("Why two windows must be same-season: the marsh's own seasonal cycle", fontsize=10)
    leg = ax.legend(frameon=False, fontsize=8, loc="lower right")
    for t_ in leg.get_texts():
        t_.set_color(CREAM)
    fig.tight_layout()
    fig.savefig(out / "seasonal_cycle.png", dpi=170, facecolor=DARK)

    # --- figure: anomaly series per labelled site ---
    real = [(sid, lab, sm) for sid, lab, sm in sites if lab in ("real", "unsure") and sm.any()]
    fig, axes = plt.subplots(
        len(real), 1, figsize=(9, 1.35 * len(real) + 0.8), sharex=True, facecolor=DARK
    )
    for ax, (sid, lab, sm) in zip(np.atleast_1d(axes), real, strict=True):
        style(ax)
        a = np.array(
            [
                np.nanmean(change.anomaly_bui[t][sm])
                if np.isfinite(change.anomaly_bui[t][sm]).mean() > 0.2
                else np.nan
                for t in range(T)
            ]
        )
        ax.axhline(0, color=CREAM, alpha=0.25, lw=0.8)
        ax.axhline(0.15, color=CREAM, alpha=0.25, lw=0.8, ls="--")
        ax.plot(x, a, "-o", color=CREAM, ms=2.5, lw=0.9, alpha=0.9)
        ax.axvspan(-0.5, S.idx(2020, 12) + 0.5, color=CREAM, alpha=0.05)
        on = next((o for s_, _, o, _ in onsets if s_ == sid), None)
        if on:
            ax.axvline(S.months.index(on), color=CREAM, lw=1.2, ls=":")
            ax.text(S.months.index(on) + 0.5, 0.42, f"onset {on:%b %Y}", color=CREAM, fontsize=7.5)
        ax.text(0.5, 0.42, f"site {sid} · {lab}", color=CREAM, fontsize=8)
        ax.set_ylim(-0.35, 0.6)
        ax.set_yticks([0, 0.3])
    axes[-1].set_xticks(ticks)
    axes[-1].set_xticklabels([str(S.months[t].year) for t in ticks])
    fig.suptitle(
        "BUI anomaly (observed − expected season) per labelled site; dotted = detected onset",
        color=CREAM,
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(out / "site_anomalies.png", dpi=170, facecolor=DARK)
    log.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
