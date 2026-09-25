# ruff: noqa: N803, N806, E501
"""Parcel-level phenology-normalised change detection (design note §5).

The v1 detector compares two windows and therefore *requires* the operator to pick
same-season windows; in a monsoon climate the seasonal swing of the built-up index (BUI =
NDBI − NDVI) is several times larger than the change threshold, so a mismatched pair floods
the result with seasonal false positives.

This module instead learns, per pixel, the expected seasonal cycle from a reference period
using a two-harmonic least-squares fit

    BUI(t) ≈ a + b·cos(2πt/12) + c·sin(2πt/12) + d·cos(4πt/12) + e·sin(4πt/12)

and flags a pixel when the *anomaly* (observed − expected) exceeds the threshold in
`persist` consecutive clear months, with the NDVI anomaly negative at the same time, and the
condition then holds in ≥ `hold_frac` of the remaining clear months (permanence — built
surface stays built). Cloudy months are skipped, not treated as evidence; months with too few
clear pixels are dropped; water-like pixels are never candidates. The first month of the
qualifying run is the onset. Parameter choices are documented in docs/design-contribution.md.

Everything is plain NumPy; no training data are needed beyond the parcel's own history.
"""

from dataclasses import dataclass

import numpy as np

N_HARM_PARAMS = 5


@dataclass(frozen=True)
class PhenologyParams:
    t_bui: float = 0.15  # anomaly threshold, same scale as the v1 ΔBUI threshold
    t_ndvi_drop: float = 0.10  # NDVI anomaly must be ≤ −t_ndvi_drop
    persist: int = 2  # consecutive clear months the anomaly must hold
    min_ref_months: int = 8  # pixels with fewer clear reference months are not modelled
    sigma_k: float = 0.0  # optional: also require anomaly ≥ sigma_k · residual std (0 = off)
    center: bool = False  # subtract the per-month median anomaly (hurt recall on Pallikaranai)
    min_clear_frac: float = 0.5  # months with fewer clear pixels than this are ignored entirely
    hold_frac: float = 0.4  # anomaly must stay true in ≥ this share of clear months after onset


@dataclass(frozen=True)
class HarmonicModel:
    coef: np.ndarray  # (5, H, W) NaN where not fitted
    resid_std: np.ndarray  # (H, W)
    n_ref: np.ndarray  # (H, W) clear reference months per pixel

    def predict(self, month_index: np.ndarray) -> np.ndarray:
        """Expected value for each month index (0 = Jan of the first year): (T, H, W)."""
        X = design(month_index)  # (T, 5)
        return np.asarray(np.einsum("tk,khw->thw", X, self.coef))


def design(month_index: np.ndarray) -> np.ndarray:
    t = np.asarray(month_index, dtype=np.float64)
    w = 2 * np.pi * t / 12.0
    return np.stack([np.ones_like(t), np.cos(w), np.sin(w), np.cos(2 * w), np.sin(2 * w)], 1)


def fit_harmonic(series: np.ndarray, month_index: np.ndarray, min_months: int = 8) -> HarmonicModel:
    """Fit the seasonal model per pixel. series: (T, H, W) with NaN for no-data."""
    T, H, W = series.shape
    X = design(month_index)
    coef = np.full((N_HARM_PARAMS, H, W), np.nan, dtype=np.float32)
    resid = np.full((H, W), np.nan, dtype=np.float32)
    flat = series.reshape(T, -1)
    valid = np.isfinite(flat)
    n_ref = valid.sum(0)
    # Group pixels by identical validity pattern so each pattern is solved once (fast path
    # for the common case where cloud gaps are AOI-wide).
    keys = np.packbits(valid, axis=0).T  # (N, ceil(T/8))
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    for g in np.unique(inverse):
        idx = np.where(inverse == g)[0]
        rows = valid[:, idx[0]]
        if rows.sum() < max(min_months, N_HARM_PARAMS + 1):
            continue
        Xg = X[rows]
        Yg = flat[rows][:, idx]  # (n, k)
        beta, *_ = np.linalg.lstsq(Xg, Yg, rcond=None)
        r = Yg - Xg @ beta
        coef[:, np.unravel_index(idx, (H, W))[0], np.unravel_index(idx, (H, W))[1]] = beta.astype(
            np.float32
        )
        resid.reshape(-1)[idx] = r.std(0, ddof=N_HARM_PARAMS).astype(np.float32)
    return HarmonicModel(coef=coef, resid_std=resid, n_ref=n_ref.reshape(H, W))


@dataclass(frozen=True)
class PhenologyChange:
    mask: np.ndarray  # (H, W) bool — pixels with a sustained anomaly at any time in the test period
    onset_index: np.ndarray  # (H, W) int, month index of onset; −1 where no change
    anomaly_bui: np.ndarray  # (T, H, W) observed − expected (NaN in cloudy months)
    anomaly_ndvi: np.ndarray  # (T, H, W)
    active: np.ndarray  # (T, H, W) bool — anomaly condition true in that month


def detect(
    bui: np.ndarray,
    ndvi: np.ndarray,
    month_index: np.ndarray,
    ref_mask: np.ndarray,
    params: PhenologyParams | None = None,
    water: np.ndarray | None = None,
) -> tuple[PhenologyChange, HarmonicModel, HarmonicModel]:
    """bui/ndvi: (T, H, W). ref_mask: (T,) bool — months used to fit the seasonal model.
    Returns change over the *non-reference* months only."""
    params = params or PhenologyParams()
    mb = fit_harmonic(bui[ref_mask], month_index[ref_mask], params.min_ref_months)
    mn = fit_harmonic(ndvi[ref_mask], month_index[ref_mask], params.min_ref_months)
    a_bui = (bui - mb.predict(month_index)).astype(np.float32)
    a_ndvi = (ndvi - mn.predict(month_index)).astype(np.float32)
    # Quality floor: a month with few clear pixels is a cloud/shadow composite, not evidence.
    clear_frac = np.isfinite(bui).reshape(bui.shape[0], -1).mean(1)
    bad = clear_frac < params.min_clear_frac
    a_bui[bad] = np.nan
    a_ndvi[bad] = np.nan
    if params.center:
        # Same idea as v1's AOI-median centring: remove whatever shifted the whole scene
        # (soil moisture, atmospheric residue) so only local departures remain.
        a_bui -= np.nanmedian(a_bui.reshape(a_bui.shape[0], -1), 1)[:, None, None]
        a_ndvi -= np.nanmedian(a_ndvi.reshape(a_ndvi.shape[0], -1), 1)[:, None, None]
    thr = np.full(a_bui.shape[1:], params.t_bui, dtype=np.float32)
    if params.sigma_k > 0:
        thr = np.maximum(thr, params.sigma_k * np.nan_to_num(mb.resid_std, nan=np.inf))
    cond = (a_bui >= thr) & (a_ndvi <= -params.t_ndvi_drop)
    if water is not None:
        # (H, W) static mask or (T, H, W) per-month mask: a pixel is never "built" while it is
        # water-like, and a pond that dries/fills is not new construction.
        cond &= ~water if water.ndim == 3 else ~water[None]
    cond &= ~ref_mask[:, None, None]  # never flag inside the reference period
    clear = np.isfinite(a_bui) & np.isfinite(a_ndvi)

    onset = _onset_from_runs(cond, clear, params.persist, params.hold_frac)
    return (
        PhenologyChange(
            mask=onset >= 0, onset_index=onset, anomaly_bui=a_bui, anomaly_ndvi=a_ndvi, active=cond
        ),
        mb,
        mn,
    )


# ---- radar (Sentinel-1 VV) and fusion ------------------------------------------------------


@dataclass(frozen=True)
class RadarPhenologyParams:
    t_sar_db: float = 2.5  # VV anomaly threshold (dB), same scale as the v1 Δσ° threshold
    persist: int = 2
    min_ref_months: int = 8
    hold_frac: float = 0.4
    min_clear_frac: float = 0.5


def detect_radar(
    vv_db: np.ndarray,
    month_index: np.ndarray,
    ref_mask: np.ndarray,
    params: RadarPhenologyParams | None = None,
    water: np.ndarray | None = None,
) -> tuple[PhenologyChange, HarmonicModel]:
    """Same seasonal-anomaly logic on VV backscatter: a new structure raises σ° permanently,
    soil-moisture seasonality does not. Returns onset per pixel like `detect`."""
    p = params or RadarPhenologyParams()
    m = fit_harmonic(vv_db[ref_mask], month_index[ref_mask], p.min_ref_months)
    a = (vv_db - m.predict(month_index)).astype(np.float32)
    clear_frac = np.isfinite(vv_db).reshape(vv_db.shape[0], -1).mean(1)
    a[clear_frac < p.min_clear_frac] = np.nan
    cond = a >= p.t_sar_db
    if water is not None:
        cond &= ~water if water.ndim == 3 else ~water[None]
    cond &= ~ref_mask[:, None, None]
    onset = _onset_from_runs(cond, np.isfinite(a), p.persist, p.hold_frac)
    return (
        PhenologyChange(
            mask=onset >= 0, onset_index=onset, anomaly_bui=a, anomaly_ndvi=a, active=cond
        ),
        m,
    )


def _onset_from_runs(
    cond: np.ndarray, clear: np.ndarray, persist: int, hold_frac: float
) -> np.ndarray:
    T, H, W = cond.shape
    run = np.zeros((H, W), dtype=np.int16)
    start = np.full((H, W), -1, dtype=np.int32)
    onset = np.full((H, W), -1, dtype=np.int32)
    for t in range(T):
        c, k = cond[t], clear[t]
        new_run = k & c & (run == 0)
        start[new_run] = t
        run = np.where(k, np.where(c, run + 1, 0), run)
        hit = (run >= persist) & (onset < 0)
        onset[hit] = start[hit]
    if hold_frac > 0:
        after = np.arange(T)[:, None, None] >= onset[None]
        n_clear = (clear & after).sum(0)
        n_true = (cond & clear & after).sum(0)
        keep = (onset >= 0) & (n_true >= hold_frac * np.maximum(n_clear, 1))
        onset = np.where(keep, onset, -1)
    return onset


def post_onset_mean(anomaly: np.ndarray, onset_index: np.ndarray) -> np.ndarray:
    """Mean anomaly from each pixel's onset to the end (NaN where no onset) — the seasonal
    analogue of v1's ΔBUI / Δσ° per-pixel layers, used for scoring fused regions."""
    T = anomaly.shape[0]
    after = np.arange(T)[:, None, None] >= np.where(onset_index >= 0, onset_index, T)[None]
    vals = np.where(after, anomaly, np.nan)
    with np.errstate(all="ignore"):
        out = np.nanmean(vals, 0)
    return np.where(onset_index >= 0, out, np.nan).astype(np.float32)
