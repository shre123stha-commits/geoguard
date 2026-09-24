# ruff: noqa: N803, N806, E501
"""Phenology-normalised change detection on a synthetic seasonal series (offline)."""

import numpy as np

from app.pipeline.phenology import PhenologyParams, detect, fit_harmonic


def _series(T: int = 60, H: int = 6, W: int = 6, seed: int = 0):  # type: ignore[no-untyped-def]
    rng = np.random.default_rng(seed)
    t = np.arange(T)
    season = -0.3 + 0.2 * np.cos(2 * np.pi * (t - 5) / 12)  # dry-season peak in May
    bui = season[:, None, None] + rng.normal(0, 0.02, (T, H, W))
    ndvi = (0.35 - 0.1 * np.cos(2 * np.pi * (t - 5) / 12))[:, None, None] + rng.normal(
        0, 0.02, (T, H, W)
    )
    return bui.astype(np.float32), ndvi.astype(np.float32), t


def test_fit_recovers_seasonal_cycle() -> None:
    bui, _, t = _series()
    m = fit_harmonic(bui[:24], t[:24])
    pred = m.predict(t)
    assert np.nanmax(np.abs(pred - bui)) < 0.12  # noise + fit error only
    assert np.all(m.n_ref == 24)


def test_step_change_is_dated_and_seasonal_swing_is_not_flagged() -> None:
    bui, ndvi, t = _series()
    ref = t < 24
    # a 2x2 block gets built in month 40: BUI up 0.3, NDVI down 0.25, permanently
    bui[40:, 1:3, 1:3] += 0.3
    ndvi[40:, 1:3, 1:3] -= 0.25
    # a transient: one dry month across the whole scene (month 45)
    bui[45] += 0.2
    ndvi[45] -= 0.15
    # a cloud gap
    bui[41] = np.nan
    ndvi[41] = np.nan
    ch, _, _ = detect(bui, ndvi, t, ref, PhenologyParams())
    assert ch.mask[1:3, 1:3].all()
    assert ch.mask.sum() == 4  # the seasonal cycle and the one-month transient are not change
    assert set(np.unique(ch.onset_index[1:3, 1:3])) == {40}


def test_water_and_reference_period_never_flag() -> None:
    bui, ndvi, t = _series()
    ref = t < 24
    bui[10:, 0, 0] += 0.5  # rises inside the reference period → absorbed by the fit / ignored
    bui[30:, 5, 5] += 0.5
    ndvi[30:, 5, 5] -= 0.3
    water = np.zeros(bui.shape, bool)
    water[:, 5, 5] = True
    ch, _, _ = detect(bui, ndvi, t, ref, PhenologyParams(), water=water)
    assert not ch.mask[5, 5]
    assert ch.onset_index[0, 0] < 0 or ch.onset_index[0, 0] >= 24
