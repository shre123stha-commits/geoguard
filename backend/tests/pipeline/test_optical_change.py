"""SYNTHETIC scene: a vegetated field where one block becomes built-up, plus a drying pond."""

import numpy as np

from app.pipeline.optical import (
    OpticalChangeParams,
    binary_opening,
    compute_indices,
    optical_change_mask,
    water_mask,
)

H = W = 20
VEG = (0.04, 0.40, 0.18)
BUILT = (0.18, 0.22, 0.30)
WATER = (0.03, 0.02, 0.01)
MUD = (0.15, 0.20, 0.25)
# Shallow water with emergent reeds (real marsh case): dark NIR/SWIR but some vegetation signal.
WET_REEDS = (0.03, 0.08, 0.04)


def _scene(fill: tuple[float, float, float]) -> list[np.ndarray]:
    return [np.full((H, W), v, dtype=np.float32) for v in fill]


def _paint(
    bands: list[np.ndarray], sl: tuple[slice, slice], val: tuple[float, float, float]
) -> None:
    for b, v in zip(bands, val, strict=True):
        b[sl] = v


def test_block_built_is_detected_and_pond_drying_is_not() -> None:
    base = _scene(VEG)
    cur = _scene(VEG)
    _paint(cur, (slice(2, 8), slice(2, 8)), BUILT)  # 6x6 new construction
    _paint(base, (slice(12, 18), slice(12, 18)), WET_REEDS)  # wet marsh in baseline ...
    _paint(cur, (slice(12, 18), slice(12, 18)), MUD)  # ... dry mud in current
    cur[0][10, 10], cur[1][10, 10], cur[2][10, 10] = BUILT  # single-pixel speck

    ib = compute_indices(*base)
    ic = compute_indices(*cur)
    res = optical_change_mask(ib, ic, tuple(base), tuple(cur))

    assert res.mask[2:8, 2:8].all()  # built block found
    assert not res.mask[12:18, 12:18].any()  # drying pond excluded (water in baseline)
    assert not res.mask[10, 10]  # speck removed by opening
    assert res.mask.sum() == 36
    assert res.water[12:18, 12:18].all()


def test_without_water_exclusion_drying_marsh_is_flagged() -> None:
    # Wet reeds -> dry mud: NDVI falls, BUI rises, so the plain rule fires; water excl. stops it.
    base, cur = _scene(WET_REEDS), _scene(MUD)
    ib, ic = compute_indices(*base), compute_indices(*cur)
    p = OpticalChangeParams(exclude_water=False, center_on_median=False, opening_radius_px=0)
    assert optical_change_mask(ib, ic, tuple(base), tuple(cur), p).mask.all()
    p2 = OpticalChangeParams(exclude_water=True, center_on_median=False, opening_radius_px=0)
    assert not optical_change_mask(ib, ic, tuple(base), tuple(cur), p2).mask.any()


def test_median_centering_removes_global_shift() -> None:
    # Whole scene brightens uniformly: with centering nothing is flagged.
    base = _scene(VEG)
    cur = [b + 0.05 for b in base]
    ib, ic = compute_indices(*base), compute_indices(*cur)
    res = optical_change_mask(ib, ic, tuple(base), tuple(cur))
    assert not res.mask.any()
    assert abs(float(np.nanmedian(res.d_bui))) < 1e-6


def test_binary_opening_removes_specks_keeps_blocks() -> None:
    m = np.zeros((10, 10), bool)
    m[1, 1] = True
    m[4:8, 4:8] = True
    out = binary_opening(m, 1)
    assert not out[1, 1] and out[4:8, 4:8].all() and out.sum() == 16
    np.testing.assert_array_equal(binary_opening(m, 0), m)


def test_water_mask_thresholds() -> None:
    nir = np.array([0.02, 0.2], np.float32)
    swir = np.array([0.01, 0.3], np.float32)
    np.testing.assert_array_equal(water_mask(nir, swir), [True, False])
