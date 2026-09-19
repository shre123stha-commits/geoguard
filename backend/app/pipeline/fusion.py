"""Decision-level fusion of optical and radar candidate regions (techspec §5.2 step 9).

Rules (defaults, tunable through FusionParams):

    | optical region | radar overlap >= overlap_threshold | class    |
    |----------------|------------------------------------|----------|
    | yes            | yes                                | high     |
    | yes            | no                                 | medium   |
    | no (radar-only)| yes                                | low      |

`sar_overlap` of an optical region = fraction of its pixels that fall inside the radar change
mask after a 1-pixel dilation (tolerates the ~1 px co-registration jitter between S1 RTC and S2).
Radar regions that touch no optical region become `low` candidates; radar regions that do touch
one are absorbed into it (their evidence is already counted in `sar_overlap`).

Score in [0, 1] (algorithm_version idx-fusion-1.0.0):

    score = 0.4 * norm(d_bui_mean,      0.15 -> 0.60)
          + 0.3 * norm(d_sigma_vv_mean, 0.0  -> 6.0 dB)
          + 0.2 * sar_overlap
          + 0.1 * compactness                      # 4*pi*A / P^2, 1 for a circle

`norm(x, lo, hi)` = clip((x - lo) / (hi - lo), 0, 1). Means are taken over the region's own pixels
(NaN-aware). The score never overrides the class; it only orders regions within a class.
"""

from dataclasses import dataclass
from math import pi
from typing import Any, Literal

import numpy as np
from scipy.ndimage import binary_dilation

from app.pipeline.vectorize import Region

ALGORITHM_VERSION = "idx-fusion-1.0.0"

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class FusionParams:
    overlap_threshold: float = 0.3
    dilate_px: int = 1
    w_optical: float = 0.4
    w_radar: float = 0.3
    w_overlap: float = 0.2
    w_compact: float = 0.1
    bui_lo: float = 0.15
    bui_hi: float = 0.60
    sar_lo_db: float = 0.0
    sar_hi_db: float = 6.0


@dataclass(frozen=True)
class FusedRegion:
    region: Region
    confidence: Confidence
    score: float
    sar_overlap: float
    d_bui_mean: float
    d_sigma_vv_mean_db: float
    compactness: float
    sources: tuple[str, ...]  # ("optical", "radar"), ("optical",) or ("radar",)

    def properties(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "score": round(self.score, 3),
            "sar_overlap": round(self.sar_overlap, 3),
            "d_bui_mean": round(self.d_bui_mean, 3),
            "d_sigma_vv_mean_db": round(self.d_sigma_vv_mean_db, 2),
            "compactness": round(self.compactness, 3),
            "sources": list(self.sources),
            "algorithm_version": ALGORITHM_VERSION,
        }


def norm(x: float, lo: float, hi: float) -> float:
    """Linear rescale of x from [lo, hi] to [0, 1], clipped; NaN -> 0."""
    if hi <= lo:
        raise ValueError("hi must be > lo")
    if np.isnan(x):
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def compactness(region: Region) -> float:
    """Polsby-Popper 4*pi*A/P^2 in the grid CRS; 1 for a circle, ~0.785 for a square."""
    p = region.geom_utm.length
    if p <= 0:
        return 0.0
    return float(np.clip(4.0 * pi * region.geom_utm.area / (p * p), 0.0, 1.0))


def overlap_fraction(region: Region, other_mask: np.ndarray, dilate_px: int) -> float:
    """Fraction of region pixels inside `other_mask` dilated by `dilate_px`."""
    m = other_mask.astype(bool)
    if dilate_px > 0:
        k = np.ones((2 * dilate_px + 1,) * 2, dtype=bool)
        m = binary_dilation(m, structure=k)
    n = int(region.pixel_mask.sum())
    if n == 0:
        return 0.0
    return float(np.count_nonzero(region.pixel_mask & m)) / n


def _nanmean(layer: np.ndarray, mask: np.ndarray) -> float:
    vals = layer[mask]
    if vals.size == 0 or np.all(np.isnan(vals)):
        return float("nan")
    return float(np.nanmean(vals))


def score_region(
    d_bui_mean: float,
    d_sigma_mean_db: float,
    sar_overlap: float,
    compact: float,
    params: FusionParams,
) -> float:
    s = (
        params.w_optical * norm(d_bui_mean, params.bui_lo, params.bui_hi)
        + params.w_radar * norm(d_sigma_mean_db, params.sar_lo_db, params.sar_hi_db)
        + params.w_overlap * float(np.clip(sar_overlap, 0.0, 1.0))
        + params.w_compact * float(np.clip(compact, 0.0, 1.0))
    )
    return float(np.clip(s, 0.0, 1.0))


def fuse(
    optical_regions: list[Region],
    radar_regions: list[Region],
    radar_mask: np.ndarray,
    d_bui: np.ndarray,
    d_sigma_vv_db: np.ndarray,
    params: FusionParams | None = None,
) -> list[FusedRegion]:
    """Assign confidence class and score to every candidate region.

    Returns optical regions (high/medium) followed by radar-only regions (low), each sorted by
    score descending within its class.
    """
    p = params or FusionParams()
    out: list[FusedRegion] = []
    optical_union = np.zeros(radar_mask.shape, dtype=bool)
    for r in optical_regions:
        optical_union |= r.pixel_mask
        ov = overlap_fraction(r, radar_mask, p.dilate_px)
        b = _nanmean(d_bui, r.pixel_mask)
        s = _nanmean(d_sigma_vv_db, r.pixel_mask)
        c = compactness(r)
        conf: Confidence = "high" if ov >= p.overlap_threshold else "medium"
        out.append(
            FusedRegion(
                region=r,
                confidence=conf,
                score=score_region(b, s, ov, c, p),
                sar_overlap=ov,
                d_bui_mean=b,
                d_sigma_vv_mean_db=s,
                compactness=c,
                sources=("optical", "radar") if conf == "high" else ("optical",),
            )
        )
    for r in radar_regions:
        # radar regions touching any optical region are absorbed by it
        if overlap_fraction(r, optical_union, p.dilate_px) > 0.0:
            continue
        b = _nanmean(d_bui, r.pixel_mask)
        s = _nanmean(d_sigma_vv_db, r.pixel_mask)
        c = compactness(r)
        out.append(
            FusedRegion(
                region=r,
                confidence="low",
                score=score_region(b, s, 0.0, c, p),
                sar_overlap=0.0,
                d_bui_mean=b,
                d_sigma_vv_mean_db=s,
                compactness=c,
                sources=("radar",),
            )
        )
    rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda f: (rank[f.confidence], -f.score))
    return out
