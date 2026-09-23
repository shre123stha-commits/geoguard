"""Phase 9.4: field photo service — GPS read, EXIF stripped, downscaled (offline)."""

import io
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.services.field_photo import PhotoError, haversine_m, read_gps, save_field_photo


def _jpeg_with_gps(lat: float, lon: float, size: tuple[int, int] = (2400, 1800)) -> bytes:
    img = Image.new("RGB", size, (90, 80, 70))
    exif = Image.Exif()
    exif[0x0110] = "TestPhone 9"  # Model — must not survive
    gps = exif.get_ifd(0x8825)
    gps[1] = "N" if lat >= 0 else "S"
    gps[2] = _to_dms(abs(lat))
    gps[3] = "E" if lon >= 0 else "W"
    gps[4] = _to_dms(abs(lon))
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _to_dms(v: float) -> tuple[float, float, float]:
    d = int(v)
    m = int((v - d) * 60)
    s = round(((v - d) * 60 - m) * 60, 3)
    return (float(d), float(m), s)


def test_reads_gps_and_strips_exif(tmp_path: Path) -> None:
    raw = _jpeg_with_gps(12.9407, 80.2201)
    assert read_gps(Image.open(io.BytesIO(raw))) == pytest.approx((80.2201, 12.9407), abs=1e-4)
    saved = save_field_photo(tmp_path, uuid.uuid4(), raw, centroid=(80.2210, 12.9400))
    out = tmp_path / saved.rel_path
    assert out.is_file() and saved.rel_path.startswith("evidence/field/")
    assert max(saved.width, saved.height) == 1600
    assert saved.meta["position_source"] == "exif"
    assert 100 < saved.meta["distance_m"] < 200  # ~125 m
    reopened = Image.open(out)
    assert not reopened.getexif()  # no Model, no GPS


def test_browser_position_fallback_and_errors(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 300))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    saved = save_field_photo(tmp_path, uuid.uuid4(), buf.getvalue(), None, (80.0, 13.0))
    assert saved.meta["position_source"] == "browser" and saved.meta["lat"] == 13.0
    assert "distance_m" not in saved.meta
    saved2 = save_field_photo(tmp_path, uuid.uuid4(), buf.getvalue(), None, None)
    assert saved2.meta["position_source"] is None and "lat" not in saved2.meta
    with pytest.raises(PhotoError):
        save_field_photo(tmp_path, uuid.uuid4(), b"not an image", None, None)
    with pytest.raises(PhotoError):
        save_field_photo(tmp_path, uuid.uuid4(), b"x" * (12 * 1024 * 1024 + 1), None, None)


def test_haversine() -> None:
    assert haversine_m((80.0, 13.0), (80.0, 13.0)) == 0
    assert haversine_m((80.0, 13.0), (80.0, 13.01)) == pytest.approx(1112, rel=0.01)
