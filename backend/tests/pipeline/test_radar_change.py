"""SYNTHETIC radar scene: flat field, a new building block (+6 dB), noise, and a water patch."""

import numpy as np

from app.pipeline.radar import RadarChangeParams, radar_change_mask, speckle_filter

H = W = 20


def _flat(v: float) -> np.ndarray:
    return np.full((H, W), v, dtype=np.float32)


def test_block_rise_detected_speck_and_water_excluded() -> None:
    rng = np.random.default_rng(1)
    vv_b = _flat(-8.0) + rng.normal(0, 0.8, (H, W)).astype(np.float32)
    vv_c = vv_b.copy()
    vv_c[3:9, 3:9] += 6.0  # new structures: strong rise
    vv_c[15, 15] += 8.0  # isolated speck
    vv_c[12:16, 2:6] += 5.0  # water patch got rough (wind) -> should be excluded
    water = np.zeros((H, W), bool)
    water[12:16, 2:6] = True
    vh_b, vh_c = vv_b - 7, vv_c - 7

    res = radar_change_mask((vv_b, vh_b), (vv_c, vh_c), water=water)

    assert res.mask[4:8, 4:8].all()  # core of the block (edges may erode by 1 px)
    assert not res.mask[15, 15]
    assert not res.mask[12:16, 2:6].any()
    assert res.mask.sum() <= 36
    assert abs(float(np.nanmedian(res.d_sigma_vv_db))) < 0.3  # centred


def test_uniform_shift_not_flagged_when_centred() -> None:
    vv_b = _flat(-8.0)
    vv_c = _flat(-4.0)  # whole scene +4 dB (e.g. soil moisture)
    res = radar_change_mask((vv_b, vv_b - 7), (vv_c, vv_c - 7))
    assert not res.mask.any()
    res2 = radar_change_mask(
        (vv_b, vv_b - 7), (vv_c, vv_c - 7), params=RadarChangeParams(center_on_median=False)
    )
    assert res2.mask.all()


def test_speckle_filter_is_nan_aware_and_smooths() -> None:
    a = _flat(-8.0)
    a[5, 5] = 10.0  # hot pixel
    a[0, 0] = np.nan
    f = speckle_filter(a, 1)
    assert f[5, 5] == -8.0  # median removed the outlier
    assert np.isnan(f[0, 0]) and f[0, 1] == -8.0  # NaN preserved, neighbours fine
    np.testing.assert_array_equal(speckle_filter(a, 0), a)
