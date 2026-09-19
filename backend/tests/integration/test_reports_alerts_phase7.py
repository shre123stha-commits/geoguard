"""Phase 7: report PDF endpoint (7.1), alert settings + dispatch on confirm + retry (7.2/7.3)."""

from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.alerts.providers import AlertError
from app.core.config import Settings
from tests.integration.conftest import ADMIN, OFFICER, Login
from tests.integration.test_detections_phase5 import _run_scan

Seeded = tuple[TestClient, Session, str]


def test_report_pdf_is_generated_and_served(
    seeded: Seeded, login: Login, settings: Settings
) -> None:
    client, db, pid = seeded
    _run_scan(db, settings, pid)
    off = login(*OFFICER)
    det_id = client.get("/api/v1/detections", headers=off).json()["features"][0]["id"]
    r = client.post(f"/api/v1/detections/{det_id}/report", headers=off)
    assert r.status_code == 201, r.text
    reps = r.json()["reports"]
    assert len(reps) == 1 and reps[0]["generated_by_name"] == "Officer"
    url = reps[0]["url"]
    assert url.startswith("/api/v1/files/reports/")
    f = client.get(url, headers=off)
    assert f.status_code == 200 and f.headers["content-type"] == "application/pdf"
    assert f.content[:5] == b"%PDF-"
    assert client.get(url).status_code == 401  # still protected
    # second report is listed newest-first
    r = client.post(f"/api/v1/detections/{det_id}/report", headers=off)
    assert len(r.json()["reports"]) == 2


def test_alert_settings_roundtrip_and_guards(seeded: Seeded, login: Login) -> None:
    client, _, _ = seeded
    adm, off = login(*ADMIN), login(*OFFICER)
    assert client.get("/api/v1/settings/alerts", headers=off).status_code == 403
    r = client.get("/api/v1/settings/alerts", headers=adm)
    assert r.status_code == 200
    assert r.json()["enabled"] is False and r.json()["available_providers"] == ["console"]
    # telegram not configured in this env → cannot be enabled
    r = client.put(
        "/api/v1/settings/alerts",
        json={"enabled": True, "provider": "telegram", "recipients": ["42"]},
        headers=adm,
    )
    assert r.status_code == 422 and "TELEGRAM_BOT_TOKEN" in r.text
    r = client.put(
        "/api/v1/settings/alerts",
        json={
            "enabled": True,
            "provider": "console",
            "min_confidence": "medium",
            "app_url": "https://gg.example/",
        },
        headers=adm,
    )
    assert r.status_code == 200, r.text
    assert r.json()["min_confidence"] == "medium" and r.json()["app_url"] == "https://gg.example"
    assert client.get("/api/v1/settings/alerts", headers=adm).json()["enabled"] is True
    # test message through console works
    assert (
        client.post(
            "/api/v1/settings/alerts/test", json={"recipient": "log"}, headers=adm
        ).status_code
        == 204
    )


def test_confirm_dispatches_alert_and_retry(
    seeded: Seeded, login: Login, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    client, db, pid = seeded
    _run_scan(db, settings, pid)
    adm, off = login(*ADMIN), login(*OFFICER)
    feats = client.get("/api/v1/detections", headers=off).json()["features"]
    det_id = feats[0]["id"]
    conf = feats[0]["properties"]["confidence"]

    # disabled → confirming writes no alert
    r = client.patch(
        f"/api/v1/detections/{det_id}/status", json={"status": "confirmed"}, headers=off
    )
    assert r.status_code == 200 and r.json()["alerts"] == []
    # reopen (admin) via dismissed → new, then enable alerts with threshold at this class
    client.patch(
        f"/api/v1/detections/{det_id}/status",
        json={"status": "dismissed", "reason_code": "other", "note": "reset for test"},
        headers=adm,
    )
    client.patch(f"/api/v1/detections/{det_id}/status", json={"status": "new"}, headers=adm)
    client.put(
        "/api/v1/settings/alerts",
        json={
            "enabled": True,
            "provider": "console",
            "min_confidence": conf,
            "recipients": ["ops-log", "duty-log"],
        },
        headers=adm,
    )

    with caplog.at_level("INFO", logger="app.alerts"):
        r = client.patch(
            f"/api/v1/detections/{det_id}/status", json={"status": "confirmed"}, headers=off
        )
    assert r.status_code == 200, r.text
    alerts = r.json()["alerts"]
    assert [a["status"] for a in alerts] == ["sent", "sent"]
    assert sorted(a["recipient"] for a in alerts) == ["duty-log", "ops-log"]
    assert "confirmed" in caplog.text and det_id in caplog.text
    assert r.json()["properties"]["status"] == "confirmed"

    # failure path: provider raises → row failed, status change still succeeded; retry works
    client.patch(
        f"/api/v1/detections/{det_id}/status",
        json={"status": "dismissed", "reason_code": "other", "note": "again"},
        headers=adm,
    )
    client.patch(f"/api/v1/detections/{det_id}/status", json={"status": "new"}, headers=adm)
    with mock.patch("app.alerts.service.build_provider") as bp:
        bp.return_value.send.side_effect = AlertError("boom")
        r = client.patch(
            f"/api/v1/detections/{det_id}/status", json={"status": "confirmed"}, headers=off
        )
    assert r.status_code == 200
    failed = [a for a in r.json()["alerts"] if a["status"] == "failed"]
    assert len(failed) == 2 and failed[0]["last_error"] == "boom" and failed[0]["attempts"] == 1
    r = client.post(f"/api/v1/detections/{det_id}/alerts/{failed[0]['id']}/retry", headers=off)
    assert r.status_code == 200
    a = next(x for x in r.json()["alerts"] if x["id"] == failed[0]["id"])
    assert a["status"] == "sent" and a["attempts"] == 2 and a["last_error"] is None
    # retrying a sent alert is refused
    assert (
        client.post(f"/api/v1/detections/{det_id}/alerts/{a['id']}/retry", headers=off).status_code
        == 409
    )
