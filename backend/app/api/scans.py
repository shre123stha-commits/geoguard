"""/scans: create (admin), list, detail, rerun, cancel (techspec §6, task 4.1)."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import ActiveUser, AdminUser, DbDep
from app.db.enums import ScanStatus
from app.db.models import Parcel, Scan
from app.pipeline.aoi import AoiError, build_aoi
from app.pipeline.fusion import ALGORITHM_VERSION
from app.repositories import DetectionRepository, ParcelRepository, ScanRepository
from app.repositories.base import from_db
from app.schemas.common import Page, PageParams, page_params
from app.schemas.scans import ScanCreate, ScanDetail, ScanOut, SceneOut

router = APIRouter(prefix="/scans", tags=["scans"])
logger = logging.getLogger(__name__)


def _out(scan: Scan, counts: dict[uuid.UUID, int]) -> ScanOut:
    o = ScanOut.model_validate(scan)
    o.detection_count = counts.get(scan.id, 0)
    return o


def _detail(scan: Scan, db: DbDep) -> ScanDetail:
    counts = DetectionRepository(db).count_by_scan([scan.id])
    base = _out(scan, counts)
    d = ScanDetail(**base.model_dump())
    d.scenes = [SceneOut.model_validate(s) for s in scan.scenes]
    d.aoi = from_db(scan.aoi_geom)
    return d


@router.get("", response_model=Page[ScanOut])
def list_scans(
    _: ActiveUser,
    db: DbDep,
    paging: Annotated[PageParams, Depends(page_params)],
    status: ScanStatus | None = None,
) -> Page[ScanOut]:
    rows, total = ScanRepository(db).list_page(paging.offset, paging.page_size, status)
    counts = DetectionRepository(db).count_by_scan([s.id for s in rows])
    return Page(
        items=[_out(s, counts) for s in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post("", response_model=ScanDetail, status_code=201)
def create_scan(body: ScanCreate, admin: AdminUser, db: DbDep) -> ScanDetail:
    prepo = ParcelRepository(db)
    parcels: list[Parcel] = []
    missing: list[uuid.UUID] = []
    for pid in dict.fromkeys(body.parcel_ids):  # de-duplicate, keep order
        p = prepo.get(pid)
        if p is None:
            missing.append(pid)
        else:
            parcels.append(p)
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown parcel id(s): {missing[:5]}")
    # Fail fast on an oversized AOI instead of queuing a scan that will fail (techspec §5.3).
    feats = [{"geometry": from_db(p.geom), "properties": {"name": p.name}} for p in parcels]
    try:
        build_aoi(feats)
    except AoiError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if body.params.mode == "seasonal":
        months = (
            (body.baseline_end.year - body.baseline_start.year) * 12
            + (body.baseline_end.month - body.baseline_start.month)
            + 1
        )
        if months < 12:
            raise HTTPException(
                status_code=422,
                detail="Seasonal mode needs a reference period of at least 12 months "
                "(24 recommended) so the model sees every season.",
            )
    scan = ScanRepository(db).create(
        parcels,
        (body.baseline_start, body.baseline_end),
        (body.current_start, body.current_end),
        body.params.model_dump(),
        ALGORITHM_VERSION,
        created_by=admin.id,
    )
    db.commit()
    db.refresh(scan)
    logger.info("scan queued", extra={"scan_id": str(scan.id), "user_id": str(admin.id)})
    return _detail(scan, db)


def _get_or_404(db: DbDep, scan_id: uuid.UUID) -> Scan:
    scan = ScanRepository(db).get(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.get("/{scan_id}", response_model=ScanDetail)
def get_scan(scan_id: uuid.UUID, _: ActiveUser, db: DbDep) -> ScanDetail:
    return _detail(_get_or_404(db, scan_id), db)


@router.post("/{scan_id}/rerun", response_model=ScanDetail, status_code=201)
def rerun_scan(scan_id: uuid.UUID, admin: AdminUser, db: DbDep) -> ScanDetail:
    """New queued scan with the same parcels, periods and params (`rerun_of` set)."""
    src = _get_or_404(db, scan_id)
    if src.status in (ScanStatus.queued, ScanStatus.running):
        raise HTTPException(status_code=409, detail="This scan has not finished yet")
    if not src.parcels:
        raise HTTPException(status_code=409, detail="The original parcels no longer exist")
    params = {k: v for k, v in src.params.items() if k != "warnings"}
    scan = ScanRepository(db).create(
        list(src.parcels),
        (src.baseline_start, src.baseline_end),
        (src.current_start, src.current_end),
        params,
        ALGORITHM_VERSION,
        created_by=admin.id,
        rerun_of=src.id,
    )
    db.commit()
    db.refresh(scan)
    return _detail(scan, db)


@router.post("/{scan_id}/cancel", response_model=ScanDetail)
def cancel_scan(scan_id: uuid.UUID, admin: AdminUser, db: DbDep) -> ScanDetail:
    scan = _get_or_404(db, scan_id)
    if not ScanRepository(db).cancel(scan):
        raise HTTPException(status_code=409, detail="Only queued scans can be cancelled")
    db.commit()
    db.refresh(scan)
    return _detail(scan, db)


@router.delete("/{scan_id}", status_code=204)
def delete_scan(
    scan_id: uuid.UUID,
    admin: AdminUser,
    db: DbDep,
    confirm: Annotated[bool, Query(description="Must be true; removes its detections too")] = False,
) -> None:
    scan = _get_or_404(db, scan_id)
    if scan.status == ScanStatus.running:
        raise HTTPException(status_code=409, detail="Cannot delete a running scan")
    if not confirm:
        raise HTTPException(status_code=409, detail="Repeat with ?confirm=true to delete the scan")
    db.delete(scan)
    db.commit()
