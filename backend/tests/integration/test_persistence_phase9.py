"""Phase 9.2: persistence count across scans, alert persistence rule, review insights."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.integration.conftest import ADMIN, Login
from tests.integration.test_detections_phase5 import _run_scan

Seeded = tuple[TestClient, Session, str]


def test_persistence_and_alert_rule(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    adm = login(*ADMIN)
    _run_scan(db, settings, pid)
    first = client.get("/api/v1/detections", headers=adm).json()["features"][0]
    assert first["properties"]["persistence"] == 1

    # Same synthetic scenes → the second scan flags the same site and links to the first.
    _run_scan(db, settings, pid)
    feats = client.get("/api/v1/detections", headers=adm).json()["features"]
    assert len(feats) == 2
    newest = next(f for f in feats if f["properties"]["matches_detection"] == first["id"])
    assert newest["properties"]["persistence"] == 2
    csv_text = client.get("/api/v1/detections/export?format=csv", headers=adm).text
    assert "seen_in_scans" in csv_text

    # Alerts on (console) with min_persistence=2: confirming the FIRST (seen once) sends
    # nothing; confirming the NEWEST (seen twice) sends.
    r = client.put(
        "/api/v1/settings/alerts",
        json={
            "enabled": True,
            "provider": "console",
            "recipients": [],
            "min_confidence": "low",
            "min_persistence": 2,
            "app_url": "",
        },
        headers=adm,
    )
    assert r.status_code == 200, r.text
    assert r.json()["min_persistence"] == 2
    d1 = client.patch(
        f"/api/v1/detections/{first['id']}/status", json={"status": "confirmed"}, headers=adm
    )
    assert d1.status_code == 200 and d1.json()["alerts"] == []
    d2 = client.patch(
        f"/api/v1/detections/{newest['id']}/status", json={"status": "confirmed"}, headers=adm
    )
    assert d2.status_code == 200 and len(d2.json()["alerts"]) == 1

    # Insights endpoint: admin only; too few labels → note, no suggestions.
    ins = client.get("/api/v1/settings/insights", headers=adm)
    assert ins.status_code == 200, ins.text
    body = ins.json()
    assert body["reviewed"] == 2 and body["confirmed"] == 2 and body["suggestions"] == []
    assert body["by_class"][0]["confidence"] == "high" and body["by_class"][0]["precision"] == 1
    assert "appear after" in body["note"] and body["min_labels"] == 10
