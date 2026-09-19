"""Sentinel-2 pure functions: reflectance offset, cloud mask, median composite (techspec §5.2 4-5).

All functions take numpy arrays and return numpy arrays. No I/O, no FastAPI.
Band arrays are float32 on the common grid; NaN means "no valid observation".
"""

from dataclasses import dataclass

import numpy as np

# Scene Classification Layer (SCL) codes, Sentinel-2 L2A.
SCL_NO_DATA = 0
SCL_SATURATED_DEFECTIVE = 1
SCL_DARK_AREA = 2
SCL_CLOUD_SHADOW = 3
SCL_VEGETATION = 4
SCL_NOT_VEGETATED = 5
SCL_WATER = 6
SCL_UNCLASSIFIED = 7
SCL_CLOUD_MEDIUM = 8
SCL_CLOUD_HIGH = 9
SCL_THIN_CIRRUS = 10
SCL_SNOW_ICE = 11

# Dropped per techspec step 4 (shadow, cloud medium/high, cirrus, saturated/defective) plus
# no-data and snow (snow never occurs in the study area but would confuse indices anywhere).
SCL_INVALID: frozenset[int] = frozenset(
    {
        SCL_NO_DATA,
        SCL_SATURATED_DEFECTIVE,
        SCL_CLOUD_SHADOW,
        SCL_CLOUD_MEDIUM,
        SCL_CLOUD_HIGH,
        SCL_THIN_CIRRUS,
        SCL_SNOW_ICE,
    }
)

# ESA processing baseline 04.00 (2022-01-25) introduced BOA_ADD_OFFSET = -1000 (D24).
BOA_OFFSET_BASELINE = "04.00"
BOA_ADD_OFFSET = 1000.0
REFLECTANCE_SCALE = 10000.0


def needs_boa_offset(processing_baseline: str | None) -> bool:
    """True when digital numbers carry the +1000 offset (baseline >= 04.00)."""
    if not processing_baseline:
        return False
    try:
        return float(processing_baseline) >= float(BOA_OFFSET_BASELINE)
    except ValueError:
        return False


def to_reflectance(dn: np.ndarray, processing_baseline: str | None) -> np.ndarray:
    """Digital numbers -> surface reflectance in [0, ~1], offset-corrected. NaN preserved."""
    out = dn.astype(np.float32, copy=True)
    if needs_boa_offset(processing_baseline):
        out -= BOA_ADD_OFFSET
    out /= REFLECTANCE_SCALE
    return out


def scl_valid_mask(scl: np.ndarray) -> np.ndarray:
    """Boolean mask, True where the pixel is usable (not cloud/shadow/cirrus/saturated/nodata)."""
    valid = ~np.isnan(scl)
    codes = np.nan_to_num(scl, nan=SCL_NO_DATA).astype(np.int16)
    for code in SCL_INVALID:
        valid &= codes != code
    return valid


@dataclass(frozen=True)
class Composite:
    """Per-period median composite. `bands` is (n_bands, H, W); `count` = valid obs per pixel."""

    bands: np.ndarray
    count: np.ndarray
    n_scenes: int


def median_composite(stack: np.ndarray, valid: np.ndarray) -> Composite:
    """Per-pixel median over scenes, ignoring invalid pixels.

    stack: (n_scenes, n_bands, H, W) float32; valid: (n_scenes, H, W) bool.
    Pixels with zero valid observations become NaN with count 0.
    """
    if stack.ndim != 4 or valid.ndim != 3 or stack.shape[0] != valid.shape[0]:
        raise ValueError("stack must be (S, B, H, W) and valid (S, H, W) with matching S")
    if stack.shape[2:] != valid.shape[1:]:
        raise ValueError("stack and valid grids differ")
    masked = np.where(valid[:, None, :, :], stack, np.nan).astype(np.float32)
    count = valid.sum(axis=0).astype(np.int16)
    with np.errstate(all="ignore"):
        # nanmedian warns on all-NaN slices; those become NaN, which is what we want.
        med = np.nanmedian(masked, axis=0).astype(np.float32)
    return Composite(bands=med, count=count, n_scenes=int(stack.shape[0]))


# ---- Spectral indices (techspec §5.2 step 6) -----------------------------------------------
# NDVI: vegetation index. Healthy plants reflect NIR strongly and absorb red -> high values.
# NDBI: built-up index. Built/bare surfaces reflect SWIR more than NIR -> positive values.
# BUI = NDBI - NDVI: pushes built-up up and vegetation down, so a veg -> built change is a big
# positive jump. All are dimensionless ratios in [-1, 1].

_DENOM_EPS = 1e-6


def _normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b), NaN where the denominator is ~0 or either input is NaN."""
    a = a.astype(np.float32, copy=False)
    b = b.astype(np.float32, copy=False)
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(denom) > _DENOM_EPS, (a - b) / denom, np.nan)
    return out.astype(np.float32)


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """NDVI = (B08 - B04) / (B08 + B04)."""
    return _normalized_difference(nir, red)


def ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """NDBI = (B11 - B08) / (B11 + B08)."""
    return _normalized_difference(swir, nir)


def bui(ndbi_arr: np.ndarray, ndvi_arr: np.ndarray) -> np.ndarray:
    """BUI = NDBI - NDVI (range [-2, 2]; higher = more built-up / bare)."""
    return (ndbi_arr.astype(np.float32) - ndvi_arr.astype(np.float32)).astype(np.float32)


@dataclass(frozen=True)
class Indices:
    ndvi: np.ndarray
    ndbi: np.ndarray
    bui: np.ndarray


def compute_indices(red: np.ndarray, nir: np.ndarray, swir: np.ndarray) -> Indices:
    """All three indices from reflectance bands on the common grid."""
    v = ndvi(nir, red)
    b = ndbi(swir, nir)
    return Indices(ndvi=v, ndbi=b, bui=bui(b, v))
