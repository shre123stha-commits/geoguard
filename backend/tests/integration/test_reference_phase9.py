"""Phase 9: reference layers + zone context/priority on detections."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.integration.conftest import ADMIN, OFFICER, PARCEL, Login
from tests.integration.test_detections_phase5 import _run_scan

Seeded = tuple[TestClient, Session, str]

# Zone covering the whole test parcel (so the detection is fully inside).
ZONE_COVERING = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": PARCEL,
            "properties": {"NAME": "Test marsh RF", "notified": 2022},
        }
    ],
}
# Zone well away from the parcel (~2 km east) — only hit through a buffer.
FAR = {
    "type": "Polygon",
    "coordinates": [
        [[80.215, 12.935], [80.22, 12.935], [80.22, 12.94], [80.215, 12.94], [80.215, 12.935]]
    ],
}


def _layer(client: TestClient, hdr: dict[str, str], **kw):  # type: ignore[no-untyped-def]
    body = {"name": "Layer", "kind": "wetland", **ZONE_COVERING, **kw}
    return client.post("/api/v1/reference-layers", json=body, headers=hdr)


def test_layer_crud_and_permissions(seeded: Seeded, login: Login) -> None:
    client, _, _ = seeded
    adm, off = login(*ADMIN), login(*OFFICER)

    assert client.get("/api/v1/reference-layers").status_code == 401
    assert _layer(client, off).status_code == 403
    r = _layer(client, adm, source="TN Forest Dept notification", source_date="2022-04-08")
    assert r.status_code == 201, r.text
    layer = r.json()["layer"]
    assert layer["feature_count"] == 1 and layer["kind"] == "wetland"
    assert layer["bounds"] and abs(layer["bounds"][0] - 80.19) < 1e-6
    lid = layer["id"]

    lst = client.get("/api/v1/reference-layers", headers=off).json()
    assert [x["id"] for x in lst["layers"]] == [lid] and "disclaimer" in lst

    fc = client.get(f"/api/v1/reference-layers/{lid}/features", headers=off).json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 1
    assert fc["features"][0]["properties"]["name"] == "Test marsh RF"
    assert fc["features"][0]["geometry"]["type"] == "MultiPolygon"

    # invalid / empty uploads
    bad = client.post(
        "/api/v1/reference-layers",
        json={
            "name": "x",
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
        },
        headers=adm,
    )
    assert bad.status_code == 422
    assert client.get("/api/v1/reference-layers", headers=adm).json()["layers"].__len__() == 1

    p = client.patch(
        f"/api/v1/reference-layers/{lid}",
        json={"is_active": False, "buffer_m": 100},
        headers=adm,
    )
    assert p.status_code == 200 and p.json()["is_active"] is False and p.json()["buffer_m"] == 100
    assert client.patch(f"/api/v1/reference-layers/{lid}", json={}, headers=off).status_code == 403

    assert client.delete(f"/api/v1/reference-layers/{lid}", headers=off).status_code == 403
    assert client.delete(f"/api/v1/reference-layers/{lid}", headers=adm).status_code == 204
    assert client.get(f"/api/v1/reference-layers/{lid}", headers=adm).status_code == 404


def test_zone_context_priority_and_filter(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    _run_scan(db, settings, pid)
    adm = login(*ADMIN)

    # No layers yet → normal priority, filter works
    fc = client.get("/api/v1/detections", headers=adm).json()
    det = fc["features"][0]
    assert det["properties"]["zone"]["priority"] == "normal"
    assert det["properties"]["zone"]["hits"] == []
    assert client.get("/api/v1/detections?in_zone=true", headers=adm).json()["total"] == 0
    assert client.get("/api/v1/detections?in_zone=false", headers=adm).json()["total"] == 1

    # Covering zone → high-confidence detection fully inside → critical
    r = _layer(client, adm, name="Pallikaranai RF", source="Ramsar", source_date="2022-04-08")
    lid = r.json()["layer"]["id"]
    d = client.get(f"/api/v1/detections/{det['id']}", headers=adm).json()
    z = d["properties"]["zone"]
    assert z["priority"] == "critical", z
    assert len(z["hits"]) == 1
    h = z["hits"][0]
    assert h["relation"] == "inside" and h["inside_pct"] == 100 and h["distance_m"] == 0
    assert h["layer_name"] == "Pallikaranai RF" and h["feature_name"] == "Test marsh RF"
    assert h["source"] == "Ramsar" and h["source_date"] == "2022-04-08"
    assert "100 % inside Test marsh RF (Pallikaranai RF)" in z["summary"]
    assert client.get("/api/v1/detections?in_zone=true", headers=adm).json()["total"] == 1

    # Deactivated layers are ignored
    client.patch(f"/api/v1/reference-layers/{lid}", json={"is_active": False}, headers=adm)
    d = client.get(f"/api/v1/detections/{det['id']}", headers=adm).json()
    assert d["properties"]["zone"]["priority"] == "normal"
    client.delete(f"/api/v1/reference-layers/{lid}", headers=adm)

    # Far zone without buffer → no hit; with a 3 km buffer → within_buffer → high (not critical)
    far = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": FAR, "properties": {}}],
    }
    r = client.post(
        "/api/v1/reference-layers",
        json={"name": "Lake", "kind": "water_body", **far},
        headers=adm,
    )
    fid = r.json()["layer"]["id"]
    d = client.get(f"/api/v1/detections/{det['id']}", headers=adm).json()
    assert d["properties"]["zone"]["priority"] == "normal"
    client.patch(f"/api/v1/reference-layers/{fid}", json={"buffer_m": 3000}, headers=adm)
    d = client.get(f"/api/v1/detections/{det['id']}", headers=adm).json()
    z = d["properties"]["zone"]
    assert z["priority"] == "high" and z["hits"][0]["relation"] == "within_buffer"
    assert 1500 < z["hits"][0]["distance_m"] < 3000
    assert "m from Lake (within 3000 m buffer)" in z["summary"]

    # Exports carry the priority
    csv_text = client.get("/api/v1/detections/export?format=csv", headers=adm).text
    assert "priority,zone_context" in csv_text and ",high," in csv_text
    gj = client.get("/api/v1/detections/export?format=geojson", headers=adm).json()
    assert gj["features"][0]["properties"]["zone"]["priority"] == "high"
