"""Offline unit tests for alert providers/settings (7.2, 7.3) and the PDF builder (7.1)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest
from PIL import Image
from pydantic import SecretStr

from app.alerts.providers import (
    AlertError,
    AlertMessage,
    ConsoleProvider,
    EmailProvider,
    TelegramProvider,
    build_provider,
)
from app.alerts.service import AlertSettings, provider_ready
from app.core.config import Settings
from app.reports.pdf import DISCLAIMER, ReportData, build_report


def test_console_provider_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="app.alerts"):
        ConsoleProvider().send("log", AlertMessage("Subj", "line1\nline2", "http://x/d/1"))
    assert "ALERT Subj → log: line1 | line2" in caplog.text


def test_provider_readiness_depends_on_env() -> None:
    env = Settings(jwt_secret=SecretStr("x"))
    assert provider_ready("console", env) is None
    assert "TELEGRAM_BOT_TOKEN" in (provider_ready("telegram", env) or "")
    assert "SMTP_HOST" in (provider_ready("email", env) or "")
    env2 = Settings(
        jwt_secret=SecretStr("x"),
        telegram_bot_token=SecretStr("123:abc"),
        smtp_host="smtp.example",
        smtp_from="a@b.c",
    )
    assert provider_ready("telegram", env2) is None and provider_ready("email", env2) is None
    with pytest.raises(AlertError):
        build_provider("pigeon", env)


def test_telegram_provider_parses_api_errors() -> None:
    p = TelegramProvider("123:abc")

    class Resp:
        def __enter__(self) -> "Resp":
            return self

        def __exit__(self, *a: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"ok": false, "description": "chat not found"}'

    with mock.patch("urllib.request.urlopen", return_value=Resp()) as m:
        with pytest.raises(AlertError, match="chat not found"):
            p.send("42", AlertMessage("s", "t"))
        req = m.call_args.args[0]
        assert req.full_url.startswith("https://api.telegram.org/bot123:abc/")
        assert b"chat_id=42" in req.data


def test_email_provider_uses_starttls_and_login() -> None:
    p = EmailProvider("smtp.example", 587, "user", "pw", "geoguard@example")
    smtp = mock.MagicMock()
    smtp.__enter__.return_value = smtp
    with mock.patch("smtplib.SMTP", return_value=smtp) as ctor:
        p.send("officer@example", AlertMessage("Subj", "Body"))
    ctor.assert_called_once_with("smtp.example", 587, timeout=mock.ANY)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("user", "pw")
    msg = smtp.send_message.call_args.args[0]
    assert msg["To"] == "officer@example" and msg["Subject"] == "Subj"


def test_alert_settings_validation() -> None:
    s = AlertSettings(recipients=[" a ", "a", "", "b"], app_url="https://gg.example/")
    assert s.recipients == ["a", "b"] and s.app_url == "https://gg.example"
    with pytest.raises(ValueError):
        AlertSettings(app_url="gg.example")


def test_pdf_builds_with_and_without_evidence(tmp_path: Path) -> None:
    img = tmp_path / "before.png"
    Image.new("RGB", (40, 40), (200, 120, 90)).save(img)
    data = ReportData(
        detection_id="b478eca5-6b76-4e12-8eab-55d7646cf026",
        parcel_name="Pallikaranai-West-1",
        parcel_category="wetland",
        confidence="high",
        score=0.44,
        status="confirmed",
        area_m2=3302,
        centroid_lon=80.19537,
        centroid_lat=12.93956,
        sources=["optical", "radar"],
        baseline=("2020-01-15", "2020-03-31"),
        current=("2023-01-15", "2023-03-31"),
        algorithm_version="idx-fusion-1.0.0",
        detected_at=datetime(2026, 9, 19, 20, 4, tzinfo=UTC),
        metrics={
            "d_bui_mean": 0.4,
            "d_ndvi_mean": -0.25,
            "d_sigma_vv_mean_db": 1.4,
            "sar_overlap": 0.45,
        },
        history=[(datetime(2026, 9, 19, 21, 0, tzinfo=UTC), "new", "confirmed", "Admin", "roof")],
        evidence={"before_rgb": img, "after_rgb": tmp_path / "missing.png"},
        generated_by="Administrator",
    )
    pdf = build_report(data, datetime(2026, 9, 20, tzinfo=UTC))
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000
    pdf2 = build_report(
        ReportData(**{**data.__dict__, "evidence": {}, "history": []}), datetime.now(UTC)
    )
    assert pdf2[:5] == b"%PDF-"
    for banned in ("violation", "illegal"):
        assert banned not in DISCLAIMER
