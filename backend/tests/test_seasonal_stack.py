"""Seasonal-model scan pieces (Phase 9.6): monthly stack builder + radar phenology + onset."""

import math
from datetime import UTC, date, datetime

import numpy as np

from app.pipeline.grid import make_grid
from app.pipeline.phenology import (
    PhenologyParams,
    RadarPhenologyParams,
    detect,
    detect_radar,
    post_onset_mean,
)
from app.pipeline.sources.base import SceneRef
from app.services.monthly_stack import build_stack, month_list

H = W = 24
BLOCK = (slice(6, 14), slice(8, 16))  # 8×8 px = 6 400 m² at 10 m
ONSET = date(2023, 4, 1)


class SyntheticSource:
    """One S2 and one S1 scene per month. Vegetation follows a yearly cycle; the BLOCK turns
    into bare/built ground from ONSET on (NIR down, SWIR up, VV up 4 dB)."""

    def __init__(self, cloudy_months: set[date] = frozenset()):
        self.cloudy = cloudy_months

    def search_optical(self, bbox, rng, cloud_max):
        m = rng[0]
        return [
            SceneRef(f"s2-{m:%Y-%m}", "sentinel2", datetime(m.year, m.month, 10, tzinfo=UTC), 5.0)
        ]

    def search_radar(self, bbox, rng):
        m = rng[0]
        return [SceneRef(f"s1-{m:%Y-%m}", "sentinel1", datetime(m.year, m.month, 12, tzinfo=UTC))]

    def read_grid(self, scene, bands, grid):
        m = date.fromisoformat(scene.acquired_at.strftime("%Y-%m") + "-01")
        phase = 2 * math.pi * (m.month - 1) / 12
        veg = 0.5 + 0.2 * math.cos(phase - 0.8)  # NDVI-ish seasonal amplitude
        built = m >= ONSET
        if scene.sensor == "sentinel2":
            red = np.full((H, W), 0.08, np.float32)
            nir = np.full((H, W), 0.10 + 0.35 * veg, np.float32)
            swir = np.full((H, W), 0.12, np.float32)
            scl = np.full((H, W), 4.0, np.float32)
            if built:
                red[BLOCK], nir[BLOCK], swir[BLOCK] = 0.20, 0.22, 0.30
            if m in self.cloudy:
                scl[:] = 9.0
            dn = np.stack([red, nir, swir]) * 10000
            return np.concatenate([dn, scl[None]]).astype(np.float32)
        vv_db = np.full((H, W), -12.0 + 1.0 * math.cos(phase), np.float32)
        if built:
            vv_db[BLOCK] += 4.0
        lin = 10 ** (vv_db / 10)
        return np.stack([lin, lin * 0.3]).astype(np.float32)


def _grid():
    return make_grid((300000.0, 1400000.0, 300000.0 + 10 * W, 1400000.0 + 10 * H), 32644)


def test_month_list_inclusive():
    ms = month_list(date(2021, 11, 15), date(2022, 2, 3))
    assert [m.strftime("%Y-%m") for m in ms] == ["2021-11", "2021-12", "2022-01", "2022-02"]


def test_stack_and_seasonal_detection(tmp_path):
    grid = _grid()
    months = month_list(date(2021, 1, 1), date(2023, 12, 1))
    src = SyntheticSource(cloudy_months={date(2022, 7, 1), date(2023, 6, 1)})
    stack = build_stack(src, grid, (80.0, 12.0, 80.1, 12.1), months, tmp_path)
    assert stack.bui.shape == (36, H, W)
    assert np.isnan(stack.bui[months.index(date(2022, 7, 1))]).all()  # cloudy month = gap
    # cached months load back identically
    stack2 = build_stack(src, grid, (80.0, 12.0, 80.1, 12.1), months, tmp_path)
    assert np.array_equal(np.nan_to_num(stack.bui), np.nan_to_num(stack2.bui))
    assert len(list(tmp_path.rglob("*.npz"))) == 36

    ref = np.array([m <= date(2022, 12, 1) for m in months])
    ch, _, _ = detect(stack.bui, stack.ndvi, stack.month_index, ref, PhenologyParams(persist=3))
    inside = np.zeros((H, W), bool)
    inside[BLOCK] = True
    assert ch.mask[inside].mean() > 0.9
    assert ch.mask[~inside].sum() == 0
    onsets = ch.onset_index[inside]
    assert months[int(np.median(onsets[onsets >= 0]))] == ONSET

    rch, _ = detect_radar(stack.vv_db, stack.month_index, ref, RadarPhenologyParams(persist=2))
    assert rch.mask[inside].mean() > 0.9
    assert rch.mask[~inside].sum() == 0
    assert months[int(np.median(rch.onset_index[inside]))] == ONSET

    d_sig = post_onset_mean(rch.anomaly_bui, rch.onset_index)
    assert np.isnan(d_sig[~inside]).all()
    assert 3.0 < float(np.nanmean(d_sig[inside])) < 5.0


def test_no_change_no_flags(tmp_path):
    grid = _grid()
    months = month_list(date(2021, 1, 1), date(2022, 12, 1))  # all before ONSET
    stack = build_stack(SyntheticSource(), grid, (80.0, 12.0, 80.1, 12.1), months, None)
    ref = np.array([m <= date(2021, 12, 1) for m in months])
    ch, _, _ = detect(stack.bui, stack.ndvi, stack.month_index, ref, PhenologyParams())
    rch, _ = detect_radar(stack.vv_db, stack.month_index, ref)
    assert ch.mask.sum() == 0 and rch.mask.sum() == 0
