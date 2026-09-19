"""Sentinel-1 pure functions: linear/dB conversion and median composite (techspec §5.2 step 5).

Backscatter (how strongly the ground reflects radar back) is stored as *linear power* (gamma0)
in RTC products. We composite in linear units and only then convert to decibels (dB), because
the median of dB values is not the dB of the median power. Variable names carry the unit:
`vv_lin` vs `vv_db`.
"""

from dataclasses import dataclass

import numpy as np

from app.pipeline.optical import Composite, binary_opening

_EPS = 1e-6


def to_db(lin: np.ndarray) -> np.ndarray:
    """Linear power -> dB. Non-positive/NaN values -> NaN."""
    lin = lin.astype(np.float32, copy=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10.0 * np.log10(np.where(lin > _EPS, lin, np.nan))
    return out.astype(np.float32)


def to_linear(db: np.ndarray) -> np.ndarray:
    return (10.0 ** (db.astype(np.float32) / 10.0)).astype(np.float32)


def radar_valid_mask(stack_lin: np.ndarray) -> np.ndarray:
    """(S, B, H, W) linear stack -> (S, H, W) True where all bands are finite and > 0."""
    return np.all(np.isfinite(stack_lin) & (stack_lin > _EPS), axis=1)


def median_composite_db(stack_lin: np.ndarray) -> Composite:
    """Median in linear power over scenes, returned in dB, with per-pixel valid counts."""
    valid = radar_valid_mask(stack_lin)
    masked = np.where(valid[:, None], stack_lin, np.nan).astype(np.float32)
    with np.errstate(all="ignore"):
        med_lin = np.nanmedian(masked, axis=0)
    return Composite(
        bands=to_db(med_lin),
        count=valid.sum(axis=0).astype(np.int16),
        n_scenes=int(stack_lin.shape[0]),
    )


# ---- Radar change mask (techspec §5.2 step 8) -----------------------------------------------
# New hard structures usually raise backscatter (walls + ground form a "double-bounce" corner
# reflector), so we look for a positive jump in VV dB between the two composites. Radar images
# are grainy ("speckle"), so a small median filter is applied before differencing.


@dataclass(frozen=True)
class RadarChangeParams:
    t_sar_db: float = 2.5  # dSigma_VV must exceed this (dB)
    speckle_radius_px: int = 1  # 3x3 median; 0 disables
    center_on_median: bool = True  # subtract AOI-wide median dSigma (calibration / moisture)
    opening_radius_px: int = 1
    use_vh: bool = False  # v1: VV only; VH kept for reporting


@dataclass(frozen=True)
class RadarChange:
    mask: np.ndarray
    d_sigma_vv_db: np.ndarray  # centred if requested
    d_sigma_vh_db: np.ndarray
    stats: dict[str, float]


def speckle_filter(db: np.ndarray, radius_px: int) -> np.ndarray:
    """Median filter in dB, NaN-aware (NaNs stay NaN, neighbours ignore them)."""
    if radius_px <= 0:
        return db.astype(np.float32, copy=False)
    from scipy.ndimage import generic_filter

    size = 2 * radius_px + 1
    out = generic_filter(db.astype(np.float32), _nanmedian_window, size=size, mode="nearest")
    out[np.isnan(db)] = np.nan
    return np.asarray(out, dtype=np.float32)


def _nanmedian_window(v: np.ndarray) -> float:
    with np.errstate(all="ignore"):
        m = np.nanmedian(v)
    return float(m) if np.isfinite(m) else np.nan


def radar_change_mask(
    baseline_db: tuple[np.ndarray, np.ndarray],
    current_db: tuple[np.ndarray, np.ndarray],
    water: np.ndarray | None = None,
    params: RadarChangeParams | None = None,
) -> RadarChange:
    """Pixels whose VV backscatter rose by more than `t_sar_db` between composites.

    baseline_db / current_db are (vv_db, vh_db) on the common grid. `water` is an optional
    bool mask of pixels to exclude (from the optical water test: wind-roughened water can
    swing by several dB without any construction).
    """
    params = params or RadarChangeParams()
    vv_b = speckle_filter(baseline_db[0], params.speckle_radius_px)
    vv_c = speckle_filter(current_db[0], params.speckle_radius_px)
    vh_b = speckle_filter(baseline_db[1], params.speckle_radius_px)
    vh_c = speckle_filter(current_db[1], params.speckle_radius_px)
    d_vv = (vv_c - vv_b).astype(np.float32)
    d_vh = (vh_c - vh_b).astype(np.float32)
    stats = {
        "d_vv_median_raw": float(np.nanmedian(d_vv)),
        "d_vh_median_raw": float(np.nanmedian(d_vh)),
    }
    if params.center_on_median:
        d_vv = d_vv - stats["d_vv_median_raw"]
        d_vh = d_vh - stats["d_vh_median_raw"]
    with np.errstate(invalid="ignore"):
        raw = d_vv > params.t_sar_db
        if params.use_vh:
            raw &= d_vh > params.t_sar_db
    raw &= ~np.isnan(d_vv)
    if water is not None:
        raw &= ~water
    stats["raw_fraction"] = float(raw.mean())
    mask = binary_opening(raw, params.opening_radius_px)
    stats["fraction"] = float(mask.mean())
    return RadarChange(mask=mask, d_sigma_vv_db=d_vv, d_sigma_vh_db=d_vh, stats=stats)
