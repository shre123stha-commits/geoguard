"""SYNTHETIC reflectance values with hand-computed index answers."""

import numpy as np
import pytest

from app.pipeline.optical import bui, compute_indices, ndbi, ndvi

# Typical Sentinel-2 surface reflectance (red, nir, swir1):
VEG = (0.04, 0.40, 0.18)  # dense vegetation
BUILT = (0.18, 0.22, 0.30)  # roof / concrete / bare soil
WATER = (0.03, 0.02, 0.01)


def test_ndvi_known_values() -> None:
    assert ndvi(np.float32(VEG[1]), np.float32(VEG[0])) == pytest.approx(
        (0.40 - 0.04) / 0.44, abs=1e-6
    )
    assert ndvi(np.float32(BUILT[1]), np.float32(BUILT[0])) == pytest.approx(0.04 / 0.40, abs=1e-6)


def test_ndbi_known_values() -> None:
    assert ndbi(np.float32(VEG[2]), np.float32(VEG[1])) == pytest.approx(
        (0.18 - 0.40) / 0.58, abs=1e-6
    )
    assert ndbi(np.float32(BUILT[2]), np.float32(BUILT[1])) == pytest.approx(0.08 / 0.52, abs=1e-6)


def test_bui_orders_veg_below_built() -> None:
    r, n, s = (np.array([VEG[i], BUILT[i], WATER[i]], dtype=np.float32) for i in range(3))
    idx = compute_indices(r, n, s)
    assert idx.ndvi[0] > 0.7 and idx.ndvi[1] < 0.2  # veg high, built low
    assert idx.bui[0] < -1.0  # vegetation strongly negative
    assert -0.1 < idx.bui[1] < 0.3  # built near zero / slightly positive
    assert idx.bui[1] - idx.bui[0] > 1.0  # a veg -> built change is a big positive dBUI
    np.testing.assert_allclose(idx.bui, bui(idx.ndbi, idx.ndvi))


def test_range_and_dtype() -> None:
    rng = np.random.default_rng(0)
    r, n, s = (rng.uniform(0.0, 1.0, (4, 5)).astype(np.float32) for _ in range(3))
    idx = compute_indices(r, n, s)
    for a in (idx.ndvi, idx.ndbi):
        assert a.dtype == np.float32 and np.all((a >= -1) & (a <= 1))
    assert idx.bui.dtype == np.float32 and np.all((idx.bui >= -2) & (idx.bui <= 2))


def test_nan_and_zero_denominator_propagate() -> None:
    nir = np.array([0.0, np.nan, 0.3], dtype=np.float32)
    red = np.array([0.0, 0.1, np.nan], dtype=np.float32)
    out = ndvi(nir, red)
    assert np.isnan(out).all()
