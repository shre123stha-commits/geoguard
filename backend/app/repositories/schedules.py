import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Parcel, ScanSchedule, ScheduleParcel


class ScheduleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, schedule_id: uuid.UUID) -> ScanSchedule | None:
        return self.db.get(ScanSchedule, schedule_id)

    def list_all(self, active_only: bool = False) -> list[ScanSchedule]:
        q = select(ScanSchedule).order_by(ScanSchedule.created_at)
        if active_only:
            q = q.where(ScanSchedule.is_active.is_(True))
        return list(self.db.scalars(q))

    def create(
        self,
        name: str,
        cron: str,
        parcels: list[Parcel],
        params: dict[str, Any],
        baseline_rule: dict[str, Any] | None = None,
        current_window_days: int = 30,
        created_by: uuid.UUID | None = None,
    ) -> ScanSchedule:
        if not parcels:
            raise ValueError("a schedule needs at least one parcel")
        s = ScanSchedule(
            name=name,
            cron=cron,
            params=params,
            baseline_rule=baseline_rule
            or {"mode": "same_season_previous_year", "window_days": current_window_days},
            current_window_days=current_window_days,
            created_by=created_by,
        )
        self.db.add(s)
        self.db.flush()
        for p in parcels:
            self.db.add(ScheduleParcel(schedule_id=s.id, parcel_id=p.id))
        self.db.flush()
        return s

    def set_active(self, s: ScanSchedule, active: bool) -> None:
        s.is_active = active
        self.db.flush()

    def list_page(self, offset: int, limit: int) -> tuple[list[ScanSchedule], int]:
        total = int(self.db.scalar(select(func.count()).select_from(ScanSchedule)) or 0)
        rows = self.db.scalars(
            select(ScanSchedule)
            .order_by(ScanSchedule.created_at, ScanSchedule.id)
            .offset(offset)
            .limit(limit)
        )
        return list(rows), total

    def set_parcels(self, s: ScanSchedule, parcels: list[Parcel]) -> None:
        if not parcels:
            raise ValueError("a schedule needs at least one parcel")
        self.db.execute(delete(ScheduleParcel).where(ScheduleParcel.schedule_id == s.id))
        for p in parcels:
            self.db.add(ScheduleParcel(schedule_id=s.id, parcel_id=p.id))
        self.db.flush()
        self.db.expire(s, ["parcels"])

    def delete(self, s: ScanSchedule) -> None:
        """Past scans keep their rows (scans.schedule_id -> NULL via FK)."""
        self.db.delete(s)
        self.db.flush()
