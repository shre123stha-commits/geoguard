import numpy as np
import pytest

from app.pipeline.radar import median_composite_db, to_db, to_linear


def test_db_roundtrip_and_known_values() -> None:
    lin = np.array([1.0, 0.1, 0.01, 0.0, np.nan], dtype=np.float32)
    db = to_db(lin)
    np.testing.assert_allclose(db[:3], [0.0, -10.0, -20.0], atol=1e-4)
    assert np.isnan(db[3]) and np.isnan(db[4])
    np.testing.assert_allclose(to_linear(db[:3]), lin[:3], rtol=1e-5)


def test_median_in_linear_then_db() -> None:
    # Pixel values 0.1, 0.1, 1.0 linear: median 0.1 -> -10 dB (a dB-median would give the same
    # here, so add an asymmetric case: 0.01, 0.1, 10 -> median 0.1 lin = -10 dB).
    stack = np.array([[[[0.01]]], [[[0.1]]], [[[10.0]]]], dtype=np.float32)  # (S=3,B=1,1,1)
    comp = median_composite_db(stack)
    assert comp.bands[0, 0, 0] == pytest.approx(-10.0, abs=1e-4)
    assert comp.count[0, 0] == 3


def test_invalid_radar_pixels_excluded() -> None:
    stack = np.array([[[[0.0]], [[0.5]]], [[[0.2]], [[0.5]]]], dtype=np.float32)  # S=2, B=2
    comp = median_composite_db(stack)
    # scene 0 has vv=0 -> invalid for that scene; only scene 1 counts.
    assert comp.count[0, 0] == 1
    assert comp.bands[0, 0, 0] == pytest.approx(to_db(np.array([0.2]))[0], abs=1e-4)
