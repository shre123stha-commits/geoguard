"""Sentinel-1 pure functions: linear/dB conversion and median composite (techspec §5.2 step 5).

Backscatter (how strongly the ground reflects radar back) is stored as *linear power* (gamma0)
in RTC products. We composite in linear units and only then convert to decibels (dB), because
the median of dB values is not the dB of the median power. Variable names carry the unit:
`vv_lin` vs `vv_db`.
"""

import numpy as np

from app.pipeline.optical import Composite

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
