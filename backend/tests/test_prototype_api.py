"""File-backed detections/scans slice (parcels moved to the DB-backed router in Phase 3)."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

SQ = {
    "type": "Polygon",
    "coordinates": [[[80.19, 12.93], [80.2, 12.93], [80.2, 12.94], [80.19, 12.94], [80.19, 12.93]]],
}


def _data_dir(tmp_path: Path) -> Path:
    (tmp_path / "samples").mkdir()
    (tmp_path / "previews").mkdir()
    (tmp_path / "samples" / "parcels.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "P1", "category": "wetland"},
                        "geometry": SQ,
                    }
                ],
            }
        )
    )
    (tmp_path / "previews" / "detections.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "parcel": "P1",
                            "area_m2": 901.0,
                            "confidence": "high",
                            "score": 0.49,
                            "sources": ["optical", "radar"],
                        },
                        "geometry": SQ,
                    }
                ],
            }
        )
    )
    return tmp_path


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=_data_dir(tmp_path), environment="test")
    return TestClient(create_app(settings))


def test_detections_served(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.get("/api/v1/detections")
        body = r.json()
        assert len(body["features"]) == 1
        assert body["features"][0]["properties"]["parcel_id"] == 1
        assert "screening aid" in body["disclaimer"]
        assert c.get("/api/v1/detections?confidence=low").json()["features"] == []
        assert c.get("/api/v1/detections/1").json()["confidence"] == "high"
        assert c.get("/api/v1/detections/99").status_code == 404


def test_status_workflow_requires_dismiss_reason(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.post("/api/v1/detections/1/status", json={"status": "dismissed"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "bad_request"
        r = c.post("/api/v1/detections/1/status", json={"status": "confirmed", "note": "seen"})
        assert r.json()["status"] == "confirmed"


def test_scan_without_composites_is_409(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.post("/api/v1/scans", json={})
        assert r.status_code == 409
        assert c.get("/api/v1/scans").json() == []
