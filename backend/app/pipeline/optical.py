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


# ---- Optical change mask (techspec §5.2 step 7, refined per tracker D30) --------------------

# Reflectance thresholds for a "water-like" pixel (very dark in NIR and SWIR). Used to exclude
# pixels that were water in either period: a pond drying out looks "built-up" to BUI.
WATER_NIR_MAX = 0.09
WATER_SWIR_MAX = 0.07


@dataclass(frozen=True)
class OpticalChangeParams:
    t_bui: float = 0.15  # dBUI must exceed this
    t_ndvi_drop: float = 0.10  # NDVI_baseline - NDVI_current must exceed this
    center_on_median: bool = True  # subtract AOI-wide median dBUI / dNDVI (radiometric shift)
    exclude_water: bool = True
    opening_radius_px: int = 1  # 3x3 opening; 0 disables


@dataclass(frozen=True)
class OpticalChange:
    mask: np.ndarray  # bool (H, W) candidate pixels
    d_bui: np.ndarray  # float32, centred if requested
    d_ndvi: np.ndarray
    water: np.ndarray  # bool, excluded water pixels
    stats: dict[str, float]


def water_mask(nir: np.ndarray, swir: np.ndarray) -> np.ndarray:
    return (nir < WATER_NIR_MAX) & (swir < WATER_SWIR_MAX)


def binary_opening(mask: np.ndarray, radius_px: int) -> np.ndarray:
    """Erode then dilate with a (2r+1)^2 square: removes specks thinner than the window."""
    if radius_px <= 0:
        return mask
    from scipy.ndimage import binary_opening as _open

    k = np.ones((2 * radius_px + 1, 2 * radius_px + 1), dtype=bool)
    return np.asarray(_open(mask, structure=k), dtype=bool)


def optical_change_mask(
    baseline: Indices,
    current: Indices,
    baseline_bands: tuple[np.ndarray, np.ndarray, np.ndarray],
    current_bands: tuple[np.ndarray, np.ndarray, np.ndarray],
    params: OpticalChangeParams | None = None,
) -> OpticalChange:
    """Pixels that turned from vegetation/soil to built-up between the two composites.

    bands tuples are (red, nir, swir) reflectance. Returns the mask plus the centred
    difference layers used to produce it, so callers can report magnitudes per region.
    """
    params = params or OpticalChangeParams()
    d_bui = (current.bui - baseline.bui).astype(np.float32)
    d_ndvi = (current.ndvi - baseline.ndvi).astype(np.float32)
    stats: dict[str, float] = {
        "d_bui_median_raw": float(np.nanmedian(d_bui)),
        "d_ndvi_median_raw": float(np.nanmedian(d_ndvi)),
    }
    if params.center_on_median:
        d_bui = d_bui - stats["d_bui_median_raw"]
        d_ndvi = d_ndvi - stats["d_ndvi_median_raw"]

    water = np.zeros(d_bui.shape, dtype=bool)
    if params.exclude_water:
        water = water_mask(baseline_bands[1], baseline_bands[2]) | water_mask(
            current_bands[1], current_bands[2]
        )

    with np.errstate(invalid="ignore"):
        raw = (d_bui > params.t_bui) & (-d_ndvi > params.t_ndvi_drop)
    raw &= ~water
    raw &= ~np.isnan(d_bui)
    stats["raw_fraction"] = float(raw.mean())
    mask = binary_opening(raw, params.opening_radius_px)
    stats["fraction"] = float(mask.mean())
    stats["water_fraction"] = float(water.mean())
    return OpticalChange(mask=mask, d_bui=d_bui, d_ndvi=d_ndvi, water=water, stats=stats)
