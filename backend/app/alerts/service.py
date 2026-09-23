"""Alert settings + dispatch (task 7.2; appflow Flow E steps 3–4).

Settings live in `app_settings` under key `alerts` (schema §4.11) so an admin can change them
in the UI; the provider *credentials* stay in environment variables (techspec §4). Sending
never blocks a status change: each recipient gets an `alerts` row, and a failed row can be
retried from the detection page.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from geoalchemy2.shape import to_shape
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.providers import AlertError, AlertMessage, build_provider
from app.core.config import Settings
from app.db.enums import AlertStatus, ConfidenceClass
from app.db.models import Alert, AppSetting, Detection

logger = logging.getLogger(__name__)

SETTINGS_KEY = "alerts"
MAX_ATTEMPTS = 5
_RANK = {ConfidenceClass.low: 0, ConfidenceClass.medium: 1, ConfidenceClass.high: 2}


class AlertSettings(BaseModel):
    enabled: bool = False
    provider: Literal["console", "telegram", "email"] = "console"
    recipients: list[str] = Field(default_factory=list, max_length=20)
    min_confidence: ConfidenceClass = ConfidenceClass.high
    # Phase 9.2 persistence rule: only alert when the same site was flagged in at least this
    # many consecutive scans (1 = every confirmed detection alerts, as before).
    min_persistence: int = Field(default=1, ge=1, le=6)
    app_url: str = ""  # public base URL used in links, e.g. https://geoguard.example

    @field_validator("recipients")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = []
        for r in v:
            r = r.strip()
            if r and r not in out:
                if len(r) > 200:
                    raise ValueError("recipient too long")
                out.append(r)
        return out

    @field_validator("app_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if v and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("app_url must start with http:// or https://")
        return v


def load_settings(db: Session, env: Settings) -> AlertSettings:
    row = db.get(AppSetting, SETTINGS_KEY)
    if row is None:
        # First run: provider + recipients from the environment; on as soon as the provider's
        # credentials are present (e.g. SMTP_* for e-mail), otherwise off with a hint in the UI.
        return AlertSettings(
            provider=env.alert_provider,
            recipients=env.alert_recipients,
            enabled=provider_ready(env.alert_provider, env) is None,
        )
    return AlertSettings.model_validate(row.value)


def save_settings(db: Session, value: AlertSettings, user_id: uuid.UUID) -> AlertSettings:
    row = db.get(AppSetting, SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=value.model_dump(mode="json"), updated_by=user_id)
        db.add(row)
    else:
        row.value = value.model_dump(mode="json")
        row.updated_by = user_id
    db.flush()
    return value


def provider_ready(name: str, env: Settings) -> str | None:
    """None if the provider can be constructed from the environment, else the reason."""
    try:
        build_provider(name, env)
    except AlertError as exc:
        return str(exc)
    return None


def compose(d: Detection, base_url: str, zone_summary: str | None = None) -> AlertMessage:
    c = to_shape(d.centroid)
    link = f"{base_url}/detections/{d.id}" if base_url else None
    zone_line = f"Zone context: {zone_summary}\n" if zone_summary else ""
    return AlertMessage(
        subject=f"GeoGuard-EO: {d.confidence.value} confidence change confirmed in {d.parcel.name}",
        text=(
            f"About {d.area_m2:,.0f} m² of likely new built-up surface was confirmed.\n"
            f"Parcel: {d.parcel.name}\n"
            f"{zone_line}"
            f"Location: {c.y:.5f}, {c.x:.5f}\n"
            f"Detection: {d.id}\n"
            "Screening result — verify on the ground before acting."
        ),
        link=link,
    )


def _zone_summary(db: Session, d: Detection) -> str | None:
    from app.repositories.reference import ReferenceRepository
    from app.services.zones import zone_context

    hits = ReferenceRepository(db).zone_hits(d)
    if not hits:
        return None
    zc = zone_context(d.confidence, hits)
    return f"{zc.summary} — priority {zc.priority}"


def _deliver(
    alert: Alert, d: Detection, cfg: AlertSettings, env: Settings, zone: str | None = None
) -> None:
    alert.attempts += 1
    try:
        build_provider(alert.provider, env).send(alert.recipient, compose(d, cfg.app_url, zone))
    except AlertError as exc:
        alert.status = AlertStatus.failed
        alert.last_error = str(exc)[:500]
        logger.warning("alert failed", extra={"detection_id": str(d.id), "step": alert.provider})
        return
    alert.status = AlertStatus.sent
    alert.sent_at = datetime.now(UTC)
    alert.last_error = None


def dispatch_for_confirmation(db: Session, env: Settings, d: Detection) -> list[Alert]:
    """Create + attempt one alert per recipient when a detection is confirmed. Caller commits."""
    cfg = load_settings(db, env)
    if not cfg.enabled or _RANK[d.confidence] < _RANK[cfg.min_confidence]:
        return []
    if cfg.min_persistence > 1:
        from app.repositories.detections import DetectionRepository

        seen = DetectionRepository(db).persistence_counts([d.id]).get(d.id, 1)
        if seen < cfg.min_persistence:
            logger.info(
                "alert suppressed by persistence rule",
                extra={"detection_id": str(d.id), "seen": seen, "need": cfg.min_persistence},
            )
            return []
    recipients = cfg.recipients or (["log"] if cfg.provider == "console" else [])
    zone = _zone_summary(db, d)
    out = []
    for r in recipients:
        a = Alert(
            id=uuid.uuid4(),
            detection_id=d.id,
            channel=cfg.provider,
            recipient=r,
            provider=cfg.provider,
            status=AlertStatus.pending,
            attempts=0,
        )
        db.add(a)
        _deliver(a, d, cfg, env, zone)
        out.append(a)
    db.flush()
    return out


def retry(db: Session, env: Settings, d: Detection, alert: Alert) -> Alert:
    if alert.status == AlertStatus.sent:
        raise ValueError("alert was already sent")
    if alert.attempts >= MAX_ATTEMPTS:
        raise ValueError(f"gave up after {MAX_ATTEMPTS} attempts")
    _deliver(alert, d, load_settings(db, env), env, _zone_summary(db, d))
    db.flush()
    return alert


def send_test(env: Settings, cfg: AlertSettings, recipient: str) -> None:
    build_provider(cfg.provider, env).send(
        recipient,
        AlertMessage(
            subject="GeoGuard-EO test alert",
            text="If you can read this, alert delivery is working.",
            link=cfg.app_url or None,
        ),
    )


def alerts_for(db: Session, detection_id: uuid.UUID) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert).where(Alert.detection_id == detection_id).order_by(Alert.created_at)
        )
    )
