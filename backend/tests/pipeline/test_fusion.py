"""Fusion rules and score on synthetic regions (offline)."""

import numpy as np
import pytest

from app.pipeline.fusion import (
    ALGORITHM_VERSION,
    FusionParams,
    compactness,
    fuse,
    norm,
    overlap_fraction,
    score_region,
)
from app.pipeline.grid import make_grid
from app.pipeline.vectorize import mask_to_regions

H, W = 40, 40
GRID = make_grid((500000.0, 1000000.0, 500000.0 + W * 10, 1000000.0 + H * 10), 32644)


def _block(r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
    m = np.zeros((H, W), dtype=bool)
    m[r0:r1, c0:c1] = True
    return m


def test_norm_clips_and_handles_nan() -> None:
    assert norm(0.15, 0.15, 0.6) == 0.0
    assert norm(0.6, 0.15, 0.6) == 1.0
    assert norm(0.375, 0.15, 0.6) == pytest.approx(0.5)
    assert norm(9.0, 0.0, 6.0) == 1.0
    assert norm(float("nan"), 0.0, 6.0) == 0.0
    with pytest.raises(ValueError):
        norm(1.0, 1.0, 1.0)


def test_compactness_square_is_pi_over_4() -> None:
    (r,) = mask_to_regions(_block(10, 20, 10, 20), GRID, simplify_m=0.0)
    assert compactness(r) == pytest.approx(np.pi / 4, abs=1e-6)


def test_overlap_fraction_with_dilation() -> None:
    (r,) = mask_to_regions(_block(10, 20, 10, 20), GRID)
    radar = _block(10, 20, 20, 25)  # adjacent column block, touching the region's right edge
    assert overlap_fraction(r, radar, dilate_px=0) == 0.0
    # 1-px dilation reaches one column (10 px) of the 100-px region
    assert overlap_fraction(r, radar, dilate_px=1) == pytest.approx(0.1)
    assert overlap_fraction(r, np.zeros((H, W), bool), 1) == 0.0


def test_confidence_table_high_medium_low() -> None:
    opt_a = _block(2, 12, 2, 12)  # optical with radar on 50 % of it -> high
    opt_b = _block(20, 30, 2, 12)  # optical, no radar -> medium
    rad_only = _block(20, 30, 25, 35)  # radar only -> low
    rad_mask = _block(2, 12, 2, 7) | rad_only
    optical = mask_to_regions(opt_a | opt_b, GRID)
    radar = mask_to_regions(rad_mask, GRID)
    assert len(optical) == 2 and len(radar) == 2
    d_bui = np.where(opt_a | opt_b, 0.4, 0.0)
    d_sig = np.where(rad_mask, 4.0, 0.0)
    fused = fuse(optical, radar, rad_mask, d_bui, d_sig)
    classes = [f.confidence for f in fused]
    assert classes == ["high", "medium", "low"]
    high, medium, low = fused
    assert high.sar_overlap == pytest.approx(0.6)  # 50 % + one dilated column
    assert high.sources == ("optical", "radar")
    assert medium.sar_overlap == 0.0 and medium.sources == ("optical",)
    assert low.sources == ("radar",) and low.sar_overlap == 0.0
    # the radar block overlapping opt_a was absorbed, not emitted twice
    assert sum(1 for f in fused if f.confidence == "low") == 1
    assert high.score > medium.score
    assert high.properties()["algorithm_version"] == ALGORITHM_VERSION


def test_overlap_threshold_is_tunable() -> None:
    opt = _block(2, 12, 2, 12)
    rad_mask = _block(2, 12, 2, 4)  # 20 % (+ one dilated column = 30 %)
    optical = mask_to_regions(opt, GRID)
    radar = mask_to_regions(rad_mask, GRID)
    d = np.zeros((H, W))
    assert fuse(optical, radar, rad_mask, d, d)[0].confidence == "high"  # 0.3 >= 0.3
    strict = FusionParams(overlap_threshold=0.5)
    assert fuse(optical, radar, rad_mask, d, d, strict)[0].confidence == "medium"


def test_score_formula_known_values() -> None:
    p = FusionParams()
    # maximum evidence -> 1.0; zero evidence -> 0.0
    assert score_region(0.6, 6.0, 1.0, 1.0, p) == pytest.approx(1.0)
    assert score_region(0.15, 0.0, 0.0, 0.0, p) == pytest.approx(0.0)
    # half of everything -> 0.5
    assert score_region(0.375, 3.0, 0.5, 0.5, p) == pytest.approx(0.5)
    # NaN inputs contribute nothing rather than poisoning the score
    assert score_region(float("nan"), float("nan"), 0.0, 0.5, p) == pytest.approx(0.05)
