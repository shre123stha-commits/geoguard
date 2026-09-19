"""Grid snapping, cache round-trip, windowed read from a small SYNTHETIC GeoTIFF (no network)."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.pipeline.cache import RasterCache
from app.pipeline.grid import make_grid
from app.pipeline.sources.base import SceneRef
from app.pipeline.sources.planetary_computer import PlanetaryComputerSource

EPSG = 32644


def test_grid_snaps_outward_to_whole_pixels() -> None:
    g = make_grid((500_003.0, 1_430_004.0, 500_097.0, 1_430_096.0), EPSG, 10.0)
    assert g.bounds == (500_000.0, 1_430_000.0, 500_100.0, 1_430_100.0)
    assert g.shape == (10, 10)
    assert g.crs == "EPSG:32644"


def test_grid_rejects_empty_bbox() -> None:
    with pytest.raises(ValueError):
        make_grid((1.0, 1.0, 1.0, 2.0), EPSG)


def test_cache_roundtrip_and_key_stability(tmp_path: Path) -> None:
    c = RasterCache(tmp_path)
    k1 = c.key("scene", ["B04"], "EPSG:32644", (0.0, 0.0, 10.0, 10.0), 10.0)
    k2 = c.key("scene", ["B04"], "EPSG:32644", (0.0, 0.0, 10.0, 10.0), 10.0)
    k3 = c.key("scene", ["B08"], "EPSG:32644", (0.0, 0.0, 10.0, 10.0), 10.0)
    assert k1 == k2 != k3
    assert c.get(k1) is None
    arr = np.arange(6, dtype=np.float32).reshape(1, 2, 3)
    c.put(k1, arr)
    np.testing.assert_array_equal(c.get(k1), arr)


def _write_tif(path: Path, data: np.ndarray, res: float, nodata: float | None = None) -> None:
    # SYNTHETIC: 20x20 px raster at 500000E / 1430200N, UTM 44N.
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        crs=f"EPSG:{EPSG}",
        transform=from_origin(500_000, 1_430_200, res, res),
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)


def test_read_grid_windows_and_resamples(tmp_path: Path) -> None:
    # 10 m band: value = row index; 20 m band (like B11): constant 7; SCL: nodata block.
    b04 = np.repeat(np.arange(20, dtype=np.uint16)[:, None], 20, axis=1)
    _write_tif(tmp_path / "B04.tif", b04, 10)
    _write_tif(tmp_path / "B11.tif", np.full((10, 10), 7, np.uint16), 20)
    scl = np.full((20, 20), 4, np.uint8)
    scl[:5, :] = 0
    _write_tif(tmp_path / "SCL.tif", scl, 10, nodata=0)
    scene = SceneRef(
        scene_id="synthetic",
        sensor="sentinel2",
        acquired_at=datetime(2023, 1, 1, tzinfo=UTC),
        assets={k: str(tmp_path / f"{k}.tif") for k in ("B04", "B11", "SCL")},
    )
    src = PlanetaryComputerSource(cache=RasterCache(tmp_path / "cache"))
    src._signed = lambda h: h  # type: ignore[method-assign]  # local files need no SAS
    # Window = rows 5..15, cols 2..12 of the source (subset, not the whole raster).
    grid = make_grid((500_020, 1_430_050, 500_120, 1_430_150), EPSG, 10)

    arr = src.read_grid(scene, ["B04", "B11", "SCL"], grid)

    assert arr.shape == (3, 10, 10) and arr.dtype == np.float32
    np.testing.assert_allclose(arr[0][:, 0], np.arange(5, 15))  # windowed correctly
    assert np.all(arr[1] == 7)  # 20 m -> 10 m
    assert np.all(np.isnan(arr[2][:0])) or np.all(arr[2] == 4)  # nodata rows were outside window
    # Second call served from cache: even with assets removed it still returns.
    (tmp_path / "B04.tif").unlink()
    np.testing.assert_array_equal(src.read_grid(scene, ["B04", "B11", "SCL"], grid), arr)


def test_scl_zero_becomes_nan(tmp_path: Path) -> None:
    scl = np.full((20, 20), 4, np.uint8)
    scl[:10, :] = 0
    _write_tif(tmp_path / "SCL.tif", scl, 10)
    scene = SceneRef(
        "s",
        "sentinel2",
        datetime(2023, 1, 1, tzinfo=UTC),
        assets={"SCL": str(tmp_path / "SCL.tif")},
    )
    src = PlanetaryComputerSource()
    src._signed = lambda h: h  # type: ignore[method-assign]
    arr = src.read_grid(scene, ["SCL"], make_grid((500_000, 1_430_000, 500_200, 1_430_200), EPSG))
    assert np.isnan(arr[0][:10]).all() and (arr[0][10:] == 4).all()
