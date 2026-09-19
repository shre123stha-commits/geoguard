"""SYNTHETIC-array tests for offset, SCL mask, and median composite."""

import numpy as np
import pytest

from app.pipeline.optical import (
    SCL_CLOUD_HIGH,
    SCL_CLOUD_SHADOW,
    SCL_NOT_VEGETATED,
    SCL_THIN_CIRRUS,
    SCL_VEGETATION,
    SCL_WATER,
    median_composite,
    needs_boa_offset,
    scl_valid_mask,
    to_reflectance,
)


@pytest.mark.parametrize(
    ("pb", "expected"),
    [
        ("02.12", False),
        ("03.01", False),
        ("04.00", True),
        ("05.10", True),
        (None, False),
        ("x", False),
    ],
)
def test_needs_boa_offset(pb: str | None, expected: bool) -> None:
    assert needs_boa_offset(pb) is expected


def test_to_reflectance_applies_offset_only_for_new_baseline() -> None:
    dn = np.array([[2000.0, np.nan]], dtype=np.float32)
    np.testing.assert_allclose(to_reflectance(dn, "02.12")[0, 0], 0.2)
    np.testing.assert_allclose(to_reflectance(dn, "05.10")[0, 0], 0.1)
    assert np.isnan(to_reflectance(dn, "05.10")[0, 1])


def test_scl_mask_keeps_land_water_drops_cloud() -> None:
    scl = np.array(
        [
            [SCL_VEGETATION, SCL_NOT_VEGETATED, SCL_WATER],
            [SCL_CLOUD_SHADOW, SCL_CLOUD_HIGH, SCL_THIN_CIRRUS],
            [0, np.nan, 7],
        ],
        dtype=np.float32,
    )
    expected = np.array([[True, True, True], [False, False, False], [False, False, True]])
    np.testing.assert_array_equal(scl_valid_mask(scl), expected)


def test_median_composite_ignores_invalid_and_counts() -> None:
    # 3 scenes, 1 band, 1x2 pixels. Pixel 0: values 1,2,9 with 9 invalid -> median 1.5, count 2.
    # Pixel 1: all invalid -> NaN, count 0.
    stack = np.array([[[[1.0, 5.0]]], [[[2.0, 6.0]]], [[[9.0, 7.0]]]], dtype=np.float32)
    valid = np.array([[[True, False]], [[True, False]], [[False, False]]])
    comp = median_composite(stack, valid)
    assert comp.bands.shape == (1, 1, 2)
    assert comp.bands[0, 0, 0] == pytest.approx(1.5)
    assert np.isnan(comp.bands[0, 0, 1])
    np.testing.assert_array_equal(comp.count, [[2, 0]])
    assert comp.n_scenes == 3


def test_median_composite_shape_errors() -> None:
    with pytest.raises(ValueError):
        median_composite(np.zeros((2, 1, 2, 2), np.float32), np.ones((3, 2, 2), bool))
