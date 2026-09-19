"""/schedules (admin): recurring scans (techspec §6/§7, appflow Flow F, task 4.6)."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import AdminUser, DbDep
from app.db.models import Parcel, Scan, ScanSchedule
from app.repositories import ParcelRepository, ScheduleRepository
from app.schemas.common import Page, PageParams, page_params
from app.schemas.scans import ScanDetail
from app.schemas.schedules import BaselineRule, ScheduleCreate, ScheduleOut, SchedulePatch
from app.services.scheduler import CronError, compute_windows, fire_schedule, next_run

router = APIRouter(prefix="/schedules", tags=["schedules"])
logger = logging.getLogger(__name__)


def _out(s: ScanSchedule, db: DbDep) -> ScheduleOut:
    o = ScheduleOut.model_validate(s)
    last = db.execute(
        select(Scan.id, Scan.status)
        .where(Scan.schedule_id == s.id)
        .order_by(Scan.created_at.desc())
        .limit(1)
    ).first()
    if last is not None:
        o.last_scan_id, o.last_scan_status = last[0], last[1].value
    return o


def _parcels(db: DbDep, ids: list[uuid.UUID]) -> list[Parcel]:
    repo = ParcelRepository(db)
    out: list[Parcel] = []
    for pid in dict.fromkeys(ids):
        p = repo.get(pid)
        if p is None:
            raise HTTPException(status_code=404, detail=f"Unknown parcel id: {pid}")
        out.append(p)
    return out


def _validate(cron: str, rule: BaselineRule, window_days: int) -> None:
    try:
        next_run(cron)
        compute_windows(rule.model_dump(exclude_none=True), window_days)
    except (CronError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("", response_model=Page[ScheduleOut])
def list_schedules(
    _: AdminUser, db: DbDep, paging: Annotated[PageParams, Depends(page_params)]
) -> Page[ScheduleOut]:
    rows, total = ScheduleRepository(db).list_page(paging.offset, paging.page_size)
    return Page(
        items=[_out(s, db) for s in rows], total=total, page=paging.page, page_size=paging.page_size
    )


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleCreate, admin: AdminUser, db: DbDep) -> ScheduleOut:
    _validate(body.cron, body.baseline_rule, body.current_window_days)
    parcels = _parcels(db, body.parcel_ids)
    s = ScheduleRepository(db).create(
        body.name.strip(),
        body.cron.strip(),
        parcels,
        body.params.model_dump(),
        body.baseline_rule.model_dump(exclude_none=True),
        body.current_window_days,
        created_by=admin.id,
    )
    s.next_run_at = next_run(s.cron)
    db.commit()
    db.refresh(s)
    logger.info("schedule created", extra={"schedule": str(s.id), "user_id": str(admin.id)})
    return _out(s, db)


def _get_or_404(db: DbDep, schedule_id: uuid.UUID) -> ScanSchedule:
    s = ScheduleRepository(db).get(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return s


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: uuid.UUID, _: AdminUser, db: DbDep) -> ScheduleOut:
    return _out(_get_or_404(db, schedule_id), db)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def patch_schedule(
    schedule_id: uuid.UUID, body: SchedulePatch, admin: AdminUser, db: DbDep
) -> ScheduleOut:
    repo = ScheduleRepository(db)
    s = _get_or_404(db, schedule_id)
    cron = (body.cron or s.cron).strip()
    rule = body.baseline_rule or BaselineRule(**s.baseline_rule)
    window = body.current_window_days or s.current_window_days
    _validate(cron, rule, window)
    if body.name is not None:
        s.name = body.name.strip()
    if body.parcel_ids is not None:
        repo.set_parcels(s, _parcels(db, body.parcel_ids))
    s.cron = cron
    s.current_window_days = window
    if body.baseline_rule is not None:
        s.baseline_rule = body.baseline_rule.model_dump(exclude_none=True)
    if body.params is not None:
        s.params = body.params.model_dump()
    if body.is_active is not None:
        s.is_active = body.is_active
    if body.cron is not None or (body.is_active and s.next_run_at is None):
        s.next_run_at = next_run(s.cron)
    db.commit()
    db.refresh(s)
    return _out(s, db)


@router.post("/{schedule_id}/run", response_model=ScanDetail, status_code=201)
def run_schedule_now(schedule_id: uuid.UUID, admin: AdminUser, db: DbDep) -> ScanDetail:
    """Queue a scan for this schedule right away (does not change next_run_at)."""
    from app.api.scans import _detail

    s = _get_or_404(db, schedule_id)
    nxt = s.next_run_at
    scan_id = fire_schedule(db, s, datetime.now(UTC))
    s.next_run_at = nxt
    if scan_id is None:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A scan for this schedule is already queued or running"
        )
    db.commit()
    scan = db.get(Scan, scan_id)
    assert scan is not None
    return _detail(scan, db)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: uuid.UUID, admin: AdminUser, db: DbDep) -> None:
    ScheduleRepository(db).delete(_get_or_404(db, schedule_id))
    db.commit()
