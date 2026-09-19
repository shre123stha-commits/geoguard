"""/settings/alerts: provider, recipients, minimum confidence (techspec §6; task 7.2)."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.alerts import service as alerts
from app.alerts.providers import AlertError
from app.api.deps import AdminUser, DbDep, SettingsDep

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)


class AlertSettingsOut(alerts.AlertSettings):
    provider_issue: str | None = None  # why the chosen provider cannot send right now
    available_providers: list[str] = []


class TestBody(BaseModel):
    recipient: str


def _out(db: DbDep, env: SettingsDep) -> AlertSettingsOut:
    cfg = alerts.load_settings(db, env)
    avail = [p for p in ("console", "telegram", "email") if alerts.provider_ready(p, env) is None]
    return AlertSettingsOut(
        **cfg.model_dump(),
        provider_issue=alerts.provider_ready(cfg.provider, env),
        available_providers=avail,
    )


@router.get("/alerts", response_model=AlertSettingsOut)
def get_alert_settings(_: AdminUser, db: DbDep, env: SettingsDep) -> AlertSettingsOut:
    return _out(db, env)


@router.put("/alerts", response_model=AlertSettingsOut)
def put_alert_settings(
    body: alerts.AlertSettings, user: AdminUser, db: DbDep, env: SettingsDep
) -> AlertSettingsOut:
    if body.enabled and body.provider != "console" and not body.recipients:
        raise HTTPException(status_code=422, detail="Add at least one recipient")
    issue = alerts.provider_ready(body.provider, env)
    if body.enabled and issue:
        raise HTTPException(status_code=422, detail=f"Provider not configured: {issue}")
    try:
        alerts.save_settings(db, body, user.id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    db.commit()
    logger.info("alert settings updated", extra={"user_id": str(user.id)})
    return _out(db, env)


@router.post("/alerts/test", status_code=204)
def test_alert(body: TestBody, _: AdminUser, db: DbDep, env: SettingsDep) -> None:
    cfg = alerts.load_settings(db, env)
    try:
        alerts.send_test(env, cfg, body.recipient.strip())
    except AlertError as exc:
        raise HTTPException(status_code=502, detail=f"Test message failed: {exc}") from None
