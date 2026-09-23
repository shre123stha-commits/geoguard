"""/parcels/{id}/timeline (Phase 9.3): monthly built-up trend for one parcel.

GET returns what has been computed so far plus job state; POST starts (or resumes) the
computation in the background. Any signed-in user may read; admins and officers may start.
"""

import logging
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import ActiveUser, DbDep, ReviewerUser, SettingsDep
from app.db.models import Parcel, ParcelTimeseries, TimelineJob
from app.services import timeline

router = APIRouter(prefix="/parcels", tags=["timeline"])
logger = logging.getLogger(__name__)


class MonthOut(BaseModel):
    month: date
    built_frac: float | None
    ndvi_mean: float | None
    valid_frac: float | None
    n_scenes: int


class JobOut(BaseModel):
    status: str
    progress: int
    message: str | None
    months_total: int
    months_done: int
    started_at: datetime
    finished_at: datetime | None


class TimelineOut(BaseModel):
    parcel_id: uuid.UUID
    t_bui: float
    months: list[MonthOut]
    onset_month: date | None
    job: JobOut | None
    running: bool
    note: str


class StartBody(BaseModel):
    months: int = Field(default=timeline.DEFAULT_MONTHS, ge=1, le=timeline.MAX_MONTHS)
    t_bui: float = Field(default=timeline.DEFAULT_T_BUI, ge=-1.0, le=1.0)


NOTE = (
    "Share of the parcel whose built-up index is above the threshold in each month's clear "
    "Sentinel-2 composite. Gaps are months without a clear view (clouds). A sustained step up "
    "marks when a change began; verify with the before/after imagery."
)


def _parcel(db: DbDep, parcel_id: uuid.UUID) -> Parcel:
    p = db.get(Parcel, parcel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return p


@router.get("/{parcel_id}/timeline", response_model=TimelineOut)
def get_timeline(
    parcel_id: uuid.UUID,
    _: ActiveUser,
    db: DbDep,
    t_bui: Annotated[float, Query(ge=-1.0, le=1.0)] = timeline.DEFAULT_T_BUI,
) -> TimelineOut:
    _parcel(db, parcel_id)
    rows = list(
        db.scalars(
            select(ParcelTimeseries)
            .where(
                ParcelTimeseries.parcel_id == parcel_id,
                # t_bui is stored as REAL (float32): compare with a tolerance, not equality
                func.abs(ParcelTimeseries.t_bui - t_bui) < 1e-4,
            )
            .order_by(ParcelTimeseries.month)
        )
    )
    job = db.get(TimelineJob, parcel_id)
    return TimelineOut(
        parcel_id=parcel_id,
        t_bui=t_bui,
        months=[
            MonthOut(
                month=r.month,
                built_frac=r.built_frac,
                ndvi_mean=r.ndvi_mean,
                valid_frac=r.valid_frac,
                n_scenes=r.n_scenes,
            )
            for r in rows
        ],
        onset_month=timeline.onset(rows),
        job=JobOut.model_validate(job, from_attributes=True) if job else None,
        running=timeline.is_running(parcel_id),
        note=NOTE,
    )


@router.post("/{parcel_id}/timeline", response_model=TimelineOut, status_code=202)
def start_timeline(
    parcel_id: uuid.UUID,
    body: StartBody,
    user: ReviewerUser,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
) -> TimelineOut:
    _parcel(db, parcel_id)
    from app.db.session import get_session_factory

    factory = getattr(request.app.state, "timeline_session_factory", None) or get_session_factory()
    source_factory = getattr(request.app.state, "timeline_source_factory", None)
    kwargs = {"source_factory": source_factory} if source_factory else {}
    started = timeline.start(factory, settings, parcel_id, body.months, body.t_bui, **kwargs)
    if not started:
        raise HTTPException(status_code=409, detail="Timeline is already being computed")
    logger.info(
        "timeline started",
        extra={"parcel_id": str(parcel_id), "user_id": str(user.id), "months": body.months},
    )
    return get_timeline(parcel_id, user, db, body.t_bui)
