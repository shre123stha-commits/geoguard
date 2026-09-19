"""Phase 5: detections list/detail (5.1), status transitions + audit (5.2), protected files
(5.3), export (5.4). Uses the synthetic offline scenes from the Phase 4 tests."""

import csv
import io
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ScanStatus
from app.repositories import ScanRepository
from app.services.scan_runner import ScanRunner
from tests.integration.conftest import ADMIN, OFFICER, Login
from tests.integration.test_scans_phase4 import _queue

Seeded = tuple[TestClient, Session, str]


def _run_scan(db: Session, settings: Settings, pid: str) -> str:
    scan_id = _queue(db, pid)
    scan = ScanRepository(db).get(scan_id)
    assert scan is not None
    ScanRunner(db, settings).run(scan)
    assert scan.status == ScanStatus.succeeded
    return str(scan_id)


def test_list_filters_and_detail(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    scan_id = _run_scan(db, settings, pid)
    off = login(*OFFICER)

    assert client.get("/api/v1/detections").status_code == 401
    r = client.get("/api/v1/detections", headers=off)
    assert r.status_code == 200, r.text
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["total"] == 1 and "disclaimer" in fc
    f = fc["features"][0]
    p = f["properties"]
    assert f["geometry"]["type"] == "MultiPolygon"
    assert p["confidence"] == "high" and p["sources"] == ["optical", "radar"]
    assert p["parcel_name"] == "Test parcel" and p["scan_id"] == scan_id
    assert len(p["centroid"]) == 2 and 80.19 < p["centroid"][0] < 80.195
    det_id = f["id"]

    q = "/api/v1/detections?"
    assert client.get(q + f"scan_id={scan_id}", headers=off).json()["total"] == 1
    assert client.get(q + f"scan_id={uuid.uuid4()}", headers=off).json()["total"] == 0
    assert client.get(q + f"parcel_id={pid}", headers=off).json()["total"] == 1
    assert client.get(q + "confidence=low", headers=off).json()["total"] == 0
    assert client.get(q + "status=new", headers=off).json()["total"] == 1
    assert client.get(q + "status=confirmed", headers=off).json()["total"] == 0
    assert client.get(q + "bbox=80.19,12.93,80.2,12.95", headers=off).json()["total"] == 1
    assert client.get(q + "bbox=81,13,81.1,13.1", headers=off).json()["total"] == 0
    assert client.get(q + "bbox=1,2,3", headers=off).status_code == 422
    assert client.get(q + "bbox=80.2,12.93,80.19,12.95", headers=off).status_code == 422
    assert client.get(q + "date_from=2999-01-01", headers=off).json()["total"] == 0
    assert client.get(q + "date_to=2000-01-01", headers=off).json()["total"] == 0
    assert client.get(q + "page=2&page_size=1", headers=off).json()["features"] == []

    d = client.get(f"/api/v1/detections/{det_id}", headers=off)
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["parcel"]["name"] == "Test parcel" and body["scan"]["id"] == scan_id
    assert body["scan"]["baseline_start"] == "2020-01-15"
    assert {e["kind"] for e in body["evidence"]} == {"before_rgb", "after_rgb", "change_map"}
    assert all(e["url"].startswith("/api/v1/files/evidence/") for e in body["evidence"])
    assert all(e["bounds"] and len(e["bounds"]) == 4 for e in body["evidence"])
    assert body["history"] == []
    assert sorted(body["allowed_transitions"]) == ["confirmed", "dismissed", "field_visit"]
    assert client.get(f"/api/v1/detections/{uuid.uuid4()}", headers=off).status_code == 404


def test_status_transitions_and_audit(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    _run_scan(db, settings, pid)
    adm, off = login(*ADMIN), login(*OFFICER)
    det_id = client.get("/api/v1/detections", headers=off).json()["features"][0]["id"]
    url = f"/api/v1/detections/{det_id}/status"

    # dismiss needs a reason code; "other" needs a note
    assert client.patch(url, json={"status": "dismissed"}, headers=off).status_code == 422
    r = client.patch(url, json={"status": "dismissed", "reason_code": "other"}, headers=off)
    assert r.status_code == 422
    assert (
        client.patch(
            url, json={"status": "dismissed", "reason_code": "nope"}, headers=off
        ).status_code
        == 422
    )

    # new -> field_visit -> confirmed (officer), both audited
    r = client.patch(url, json={"status": "field_visit", "note": "visit planned"}, headers=off)
    assert r.status_code == 200, r.text
    assert r.json()["properties"]["status"] == "field_visit"
    assert len(r.json()["history"]) == 1  # response must include the audit row just written
    assert sorted(r.json()["allowed_transitions"]) == ["confirmed", "dismissed"]
    # same status again → 409; invalid jump → 409
    assert client.patch(url, json={"status": "field_visit"}, headers=off).status_code == 409
    assert client.patch(url, json={"status": "new"}, headers=off).status_code == 409
    r = client.patch(url, json={"status": "confirmed"}, headers=off)
    assert r.status_code == 200 and r.json()["properties"]["status"] == "confirmed"
    # confirmed -> dismissed allowed as a correction, with reason
    r = client.patch(url, json={"status": "dismissed", "reason_code": "seasonal"}, headers=off)
    assert r.status_code == 200 and r.json()["properties"]["status"] == "dismissed"
    assert r.json()["properties"]["status_note"] == "seasonal"
    # officer cannot reopen; admin can
    assert client.patch(url, json={"status": "new"}, headers=off).status_code == 403
    assert r.json()["allowed_transitions"] == []
    r = client.patch(url, json={"status": "new", "note": "reopened for a second look"}, headers=adm)
    assert r.status_code == 200 and r.json()["properties"]["status"] == "new"

    hist = r.json()["history"]
    assert [h["to_status"] for h in hist] == ["new", "dismissed", "confirmed", "field_visit"]
    assert hist[0]["from_status"] == "dismissed" and hist[0]["changed_by_name"] == "Admin"
    assert hist[1]["reason_code"] == "seasonal" and hist[-1]["note"] == "visit planned"
    assert hist[-1]["changed_by_name"] == "Officer"
    # filter by status reflects the changes
    assert client.get("/api/v1/detections?status=new", headers=off).json()["total"] == 1


def test_files_route_requires_auth_and_blocks_traversal(
    seeded: Seeded, login: Login, settings: Settings
) -> None:
    client, db, pid = seeded
    _run_scan(db, settings, pid)
    off = login(*OFFICER)
    det = client.get("/api/v1/detections", headers=off).json()["features"][0]
    detail = client.get(f"/api/v1/detections/{det['id']}", headers=off).json()
    url = detail["evidence"][0]["url"]

    assert client.get(url).status_code == 401
    r = client.get(url, headers=off)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    (settings.data_dir / "secret.png").write_bytes(b"x")
    assert client.get("/api/v1/files/secret.png", headers=off).status_code == 404
    assert client.get("/api/v1/files/evidence/../secret.png", headers=off).status_code == 404
    assert client.get("/api/v1/files/evidence/nope/x.png", headers=off).status_code == 404


def test_export_geojson_and_csv(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    scan_id = _run_scan(db, settings, pid)
    off = login(*OFFICER)

    r = client.get("/api/v1/detections/export", headers=off)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/geo+json")
    assert "detections-" in r.headers["content-disposition"]
    gj = json.loads(r.content)
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 1
    assert gj["features"][0]["properties"]["scan_id"] == scan_id

    r = client.get("/api/v1/detections/export?format=csv&confidence=high", headers=off)
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")  # BOM stripped
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["confidence"] == "high" and row["sources"] == "optical+radar"
    assert row["wkt"].startswith("MULTIPOLYGON") and float(row["area_m2"]) > 8000
    assert float(row["lon"]) > 80 and row["status"] == "new"

    empty = client.get("/api/v1/detections/export?format=csv&confidence=low", headers=off)
    assert len(list(csv.reader(io.StringIO(empty.content.decode("utf-8-sig"))))) == 1
    assert client.get("/api/v1/detections/export?format=xlsx", headers=off).status_code == 422
    assert client.get("/api/v1/detections/export").status_code == 401
