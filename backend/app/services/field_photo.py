"""Field-visit photos (Phase 9.4).

A phone photo is re-encoded with Pillow (max 1600 px, JPEG q85) so EXIF — including the
device serial and precise GPS — is *not* stored in the file. The GPS position, if present,
is read once and stored in `evidence_files.meta` together with the distance from the
detection centroid, so a reviewer can see the photo was taken at the site.
"""

import io
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 12 * 1024 * 1024
MAX_PX = 1600


class PhotoError(ValueError):
    pass


@dataclass(frozen=True)
class SavedPhoto:
    rel_path: str  # relative to data_dir, starts with "evidence/"
    width: int
    height: int
    meta: dict[str, Any]


def _ratio(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return float("nan")


def _dms(vals: Any, ref: str | None) -> float | None:
    try:
        d, m, s = (_ratio(x) for x in vals)
    except (TypeError, ValueError):
        return None
    if any(math.isnan(x) for x in (d, m, s)):
        return None
    out = d + m / 60 + s / 3600
    return -out if ref in ("S", "W") else out


def read_gps(img: Image.Image) -> tuple[float, float] | None:
    """(lon, lat) from EXIF GPS IFD, or None."""
    try:
        exif = img.getexif()
        gps = exif.get_ifd(0x8825)
    except Exception:  # noqa: BLE001 - malformed EXIF is common on phones
        return None
    if not gps:
        return None
    lat = _dms(gps.get(2), gps.get(1))
    lon = _dms(gps.get(4), gps.get(3))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (lon, lat)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def save_field_photo(
    data_dir: Path,
    detection_id: uuid.UUID,
    raw: bytes,
    centroid: tuple[float, float] | None,
    browser_position: tuple[float, float] | None = None,
) -> SavedPhoto:
    """Validate, downscale, strip metadata, write JPEG; return path + geotag metadata."""
    if len(raw) > MAX_BYTES:
        raise PhotoError("Photo is larger than 12 MB")
    try:
        img: Image.Image = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise PhotoError("File is not a readable image (JPEG/PNG/HEIC-as-JPEG)") from None
    gps = read_gps(img) or browser_position
    source = "exif" if read_gps(img) else ("browser" if browser_position else None)
    img = ImageOps.exif_transpose(img) or img
    img = img.convert("RGB")
    img.thumbnail((MAX_PX, MAX_PX))
    clean = Image.new("RGB", img.size)
    clean.putdata(list(img.getdata()))  # drops EXIF/ICC/XMP payloads

    rel = Path("evidence") / "field" / str(detection_id)[:8] / f"{uuid.uuid4().hex[:12]}.jpg"
    out = data_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    clean.save(out, "JPEG", quality=85, optimize=True)

    meta: dict[str, Any] = {
        "taken_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "position_source": source,
    }
    if gps:
        meta["lon"], meta["lat"] = round(gps[0], 6), round(gps[1], 6)
        if centroid:
            meta["distance_m"] = round(haversine_m(gps, centroid))
    return SavedPhoto(rel.as_posix(), clean.width, clean.height, meta)
