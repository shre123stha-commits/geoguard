from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.api import health as health_module
from app.main import create_app
from app.services.health import HealthReport, check_health


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def test_health_returns_200_when_db_ok(client: TestClient) -> None:
    fake = HealthReport(status="ok", database="ok", postgis="3.4", migration=None)
    with patch.object(health_module, "check_health", return_value=fake):
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
    assert r.json()["postgis"] == "3.4"


def test_health_is_mounted_under_api_prefix(client: TestClient) -> None:
    fake = HealthReport(status="ok", database="ok", postgis=None, migration=None)
    with patch.object(health_module, "check_health", return_value=fake):
        assert client.get("/api/v1/health").status_code == 200


def test_check_health_reports_degraded_when_db_unreachable() -> None:
    bad: Engine = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/nope")
    report = check_health(bad)
    assert report.status == "degraded"
    assert report.database == "error"


def test_errors_use_standard_format(client: TestClient) -> None:
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "not_found"
