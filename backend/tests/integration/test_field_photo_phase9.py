"""Phase 9.4: field-photo upload endpoint."""

import io

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.integration.conftest import ADMIN, OFFICER, Login
from tests.integration.test_detections_phase5 import _run_scan

Seeded = tuple[TestClient, Session, str]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (120, 110, 100)).save(buf, "PNG")
    return buf.getvalue()


def test_field_photo_upload(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    adm, off = login(*ADMIN), login(*OFFICER)
    _run_scan(db, settings, pid)
    det = client.get("/api/v1/detections", headers=adm).json()["features"][0]
    did = det["id"]
    url = f"/api/v1/detections/{did}/field-photo"

    # sign-in required
    r = client.post(url, files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 401

    lon, lat = det["properties"]["centroid"]
    r = client.post(
        url,
        files={"file": ("a.png", _png(), "image/png")},
        data={"lon": str(lon + 0.0005), "lat": str(lat), "note": "seen from the road"},
        headers=off,
    )
    assert r.status_code == 201, r.text
    photos = [e for e in r.json()["evidence"] if e["kind"] == "field_photo"]
    assert len(photos) == 1
    m = photos[0]["meta"]
    assert m["position_source"] == "browser" and 40 < m["distance_m"] < 70
    assert m["note"] == "seen from the road"

    # the stored file is served through the protected files route
    f = client.get(photos[0]["url"], headers=adm)
    assert f.status_code == 200 and f.headers["content-type"] == "image/jpeg"
    assert client.get(photos[0]["url"]).status_code == 401

    r = client.post(url, files={"file": ("a.txt", b"hello", "text/plain")}, headers=off)
    assert r.status_code == 422
