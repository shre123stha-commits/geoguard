import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.enums import PeriodType, ScanStatus, SensorType
from app.db.models import Parcel, Scan, ScanParcel, ScanScene


class ScanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, scan_id: uuid.UUID) -> Scan | None:
        return self.db.get(Scan, scan_id)

    def list_all(self, status: ScanStatus | None = None, limit: int = 100) -> list[Scan]:
        q = select(Scan).order_by(Scan.created_at.desc()).limit(limit)
        if status:
            q = q.where(Scan.status == status)
        return list(self.db.scalars(q))

    def list_page(
        self, offset: int, limit: int, status: ScanStatus | None = None
    ) -> tuple[list[Scan], int]:
        q = select(Scan)
        if status:
            q = q.where(Scan.status == status)
        total = int(self.db.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = self.db.scalars(
            q.order_by(Scan.created_at.desc(), Scan.id).offset(offset).limit(limit)
        )
        return list(rows), total

    def claim_next(self) -> Scan | None:
        """Atomically take the oldest queued scan (techspec §7: FOR UPDATE SKIP LOCKED).

        Marks it `running` in the same transaction and commits, so other workers skip it.
        """
        scan = self.db.scalar(
            select(Scan)
            .where(Scan.status == ScanStatus.queued)
            .order_by(Scan.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if scan is None:
            self.db.rollback()
            return None
        scan.status = ScanStatus.running
        scan.started_at = datetime.now(UTC)
        scan.step = "claimed"
        scan.message = "Starting"
        self.db.commit()
        return scan

    def recover_stale(self, older_than: timedelta) -> int:
        """Mark `running` scans that started before now-older_than as failed (worker_restart)."""
        cutoff = datetime.now(UTC) - older_than
        res = self.db.execute(
            update(Scan)
            .where(Scan.status == ScanStatus.running)
            .where((Scan.started_at.is_(None)) | (Scan.started_at < cutoff))
            .values(
                status=ScanStatus.failed,
                error_code="worker_restart",
                message="The worker restarted while this scan was running. Re-run it.",
                finished_at=datetime.now(UTC),
            )
        )
        self.db.commit()
        return int(getattr(res, "rowcount", 0) or 0)

    def cancel(self, scan: Scan) -> bool:
        if scan.status != ScanStatus.queued:
            return False
        scan.status = ScanStatus.cancelled
        scan.finished_at = datetime.now(UTC)
        scan.message = "Cancelled before it started"
        self.db.flush()
        return True

    def create(
        self,
        parcels: list[Parcel],
        baseline: tuple[date, date],
        current: tuple[date, date],
        params: dict[str, Any],
        algorithm_version: str,
        created_by: uuid.UUID | None = None,
        rerun_of: uuid.UUID | None = None,
        schedule_id: uuid.UUID | None = None,
    ) -> Scan:
        if not parcels:
            raise ValueError("a scan needs at least one parcel")
        scan = Scan(
            baseline_start=baseline[0],
            baseline_end=baseline[1],
            current_start=current[0],
            current_end=current[1],
            params=params,
            algorithm_version=algorithm_version,
            created_by=created_by,
            rerun_of=rerun_of,
            schedule_id=schedule_id,
        )
        self.db.add(scan)
        self.db.flush()
        for p in parcels:
            self.db.add(ScanParcel(scan_id=scan.id, parcel_id=p.id))
        self.db.flush()
        return scan

    def set_progress(
        self, scan: Scan, step: str, progress: int, message: str | None = None
    ) -> None:
        scan.step = step
        scan.progress = max(0, min(100, progress))
        if message is not None:
            scan.message = message
        if scan.status == ScanStatus.queued:
            scan.status = ScanStatus.running
            scan.started_at = datetime.now(UTC)
        self.db.flush()

    def finish(
        self,
        scan: Scan,
        status: ScanStatus,
        message: str | None = None,
        error_code: str | None = None,
    ) -> None:
        scan.status = status
        scan.progress = 100 if status == ScanStatus.succeeded else scan.progress
        scan.message = message
        scan.error_code = error_code
        scan.finished_at = datetime.now(UTC)
        self.db.flush()

    def add_scene(
        self,
        scan: Scan,
        sensor: SensorType,
        period: PeriodType,
        scene_id: str,
        acquired_at: datetime,
        cloud_cover: float | None = None,
        orbit: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ScanScene:
        scene = ScanScene(
            scan_id=scan.id,
            sensor=sensor,
            period=period,
            scene_id=scene_id,
            acquired_at=acquired_at,
            cloud_cover=cloud_cover,
            orbit=orbit,
            meta=meta,
        )
        self.db.add(scene)
        self.db.flush()
        return scene

    def parcel_ids(self, scan: Scan) -> list[uuid.UUID]:
        return list(
            self.db.scalars(select(ScanParcel.parcel_id).where(ScanParcel.scan_id == scan.id))
        )
