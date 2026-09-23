"""/settings/alerts: provider, recipients, minimum confidence (techspec §6; task 7.2)."""

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.alerts import service as alerts
from app.alerts.providers import AlertError
from app.api.deps import AdminUser, DbDep, SettingsDep

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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
    if body.provider == "email":
        bad = [r for r in body.recipients if not _EMAIL.match(r)]
        if bad:
            raise HTTPException(status_code=422, detail=f"Not an e-mail address: {bad[0]}")
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
    if cfg.provider == "email" and not _EMAIL.match(body.recipient.strip()):
        raise HTTPException(
            status_code=422, detail=f"'{body.recipient.strip()}' is not an e-mail address"
        )
    try:
        alerts.send_test(env, cfg, body.recipient.strip())
    except AlertError as exc:
        raise HTTPException(status_code=502, detail=f"Test message failed: {exc}") from None


# ---------- Phase 9.2: review insights ----------


class ClassStatOut(BaseModel):
    confidence: str
    confirmed: int
    dismissed: int
    precision: float | None


class SuggestionOut(BaseModel):
    param: str
    current: float
    suggested: float
    keeps_confirmed: int
    drops_dismissed: int
    of_confirmed: int
    of_dismissed: int
    text: str


class InsightsOut(BaseModel):
    reviewed: int
    confirmed: int
    dismissed: int
    by_class: list[ClassStatOut]
    dismiss_reasons: dict[str, int]
    suggestions: list[SuggestionOut]
    note: str
    min_labels: int


@router.get("/insights", response_model=InsightsOut)
def review_insights(_: AdminUser, db: DbDep) -> InsightsOut:
    """What the confirm/dismiss history says about precision and thresholds. Advisory only."""
    from app.repositories import DetectionRepository
    from app.schemas.scans import ScanParamsIn
    from app.services import insights

    defaults = ScanParamsIn()
    rows = DetectionRepository(db).reviewed_samples()
    ins = insights.compute(rows, defaults.t_bui, defaults.t_sar_db)
    return InsightsOut(
        reviewed=ins.reviewed,
        confirmed=ins.confirmed,
        dismissed=ins.dismissed,
        by_class=[
            ClassStatOut(
                confidence=c.confidence,
                confirmed=c.confirmed,
                dismissed=c.dismissed,
                precision=c.precision,
            )
            for c in ins.by_class
        ],
        dismiss_reasons=ins.dismiss_reasons,
        suggestions=[SuggestionOut(**s.__dict__) for s in ins.suggestions],
        note=ins.note,
        min_labels=insights.MIN_LABELS,
    )
