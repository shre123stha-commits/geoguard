import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
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
