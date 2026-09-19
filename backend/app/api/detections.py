"""/detections: list (filters, bbox, pagination), export, detail, status transitions with
audit rows (techspec §6; appflow Flow D; tasks 5.1, 5.2, 5.4)."""

import csv
import io
import json
import logging
import uuid
from collections.abc import Iterator
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from geoalchemy2.shape import to_shape
from pydantic import ValidationError

from app.api.deps import ActiveUser, DbDep, ReviewerUser
from app.db.enums import ConfidenceClass, DetectionStatus, UserRole
from app.db.models import Detection, User
from app.repositories import DetectionRepository, UserRepository
from app.repositories.base import from_db
from app.schemas.detections import (
    ADMIN_ONLY_TRANSITIONS,
    TRANSITIONS,
    DetectionDetail,
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionMetrics,
    DetectionProps,
    EvidenceOut,
    HistoryOut,
    ScanSummary,
    StatusChange,
)

router = APIRouter(prefix="/detections", tags=["detections"])
logger = logging.getLogger(__name__)

MAX_EXPORT_ROWS = 20_000


# ---------- filters ----------


class Filters:
    """Query parameters shared by list and export (techspec §6: scan, parcel, class, status,
    date, bbox)."""

    def __init__(
        self,
        scan_id: uuid.UUID | None = None,
        parcel_id: uuid.UUID | None = None,
        confidence: ConfidenceClass | None = None,
        status: DetectionStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        bbox: Annotated[str | None, Query(description="minLon,minLat,maxLon,maxLat")] = None,
    ) -> None:
        self.kwargs: dict[str, Any] = {
            "scan_id": scan_id,
            "parcel_id": parcel_id,
            "confidence": confidence,
            "status": status,
            "since": datetime.combine(date_from, time.min) if date_from else None,
            # inclusive end date → strictly before the next midnight
            "until": datetime.combine(date_to, time.max) if date_to else None,
            "bbox": _parse_bbox(bbox),
        }


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None or raw == "":
        return None
    try:
        parts = [float(x) for x in raw.split(",")]
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox must be four numbers") from None
    if len(parts) != 4:
        raise HTTPException(status_code=422, detail="bbox must be minLon,minLat,maxLon,maxLat")
    minx, miny, maxx, maxy = parts
    if not (-180 <= minx < maxx <= 180 and -90 <= miny < maxy <= 90):
        raise HTTPException(status_code=422, detail="bbox is outside EPSG:4326 range or inverted")
    return (minx, miny, maxx, maxy)


# ---------- serialisation ----------


def _sources(d: Detection) -> list[str]:
    out = []
    if d.optical_detected:
        out.append("optical")
    if d.radar_detected:
        out.append("radar")
    return out


def _props(d: Detection) -> DetectionProps:
    c = to_shape(d.centroid)
    return DetectionProps(
        id=d.id,
        scan_id=d.scan_id,
        parcel_id=d.parcel_id,
        parcel_name=d.parcel.name,
        confidence=d.confidence,
        score=d.score,
        area_m2=d.area_m2,
        sources=_sources(d),
        metrics=DetectionMetrics(
            d_bui_mean=d.d_bui_mean,
            d_ndvi_mean=d.d_ndvi_mean,
            d_sigma_vv_mean_db=d.d_sigma_vv_mean,
            sar_overlap=d.sar_overlap,
        ),
        status=d.status,
        status_note=d.status_note,
        reviewed_at=d.reviewed_at,
        matches_detection=d.matches_detection,
        created_at=d.created_at,
        centroid=[round(c.x, 6), round(c.y, 6)],
    )


def _feature(d: Detection) -> DetectionFeature:
    return DetectionFeature(id=d.id, geometry=from_db(d.geom) or {}, properties=_props(d))


def allowed_transitions(d: Detection, user: User) -> list[DetectionStatus]:
    out = []
    for to in TRANSITIONS.get(d.status, set()):
        if (d.status, to) in ADMIN_ONLY_TRANSITIONS and user.role != UserRole.admin:
            continue
        out.append(to)
    return sorted(out, key=lambda s: s.value)


def _detail(d: Detection, db: DbDep, user: User) -> DetectionDetail:
    names = UserRepository(db).names_for([h.changed_by for h in d.history if h.changed_by])
    history = []
    for h in d.history:
        ho = HistoryOut.model_validate(h)
        ho.changed_by_name = names.get(h.changed_by) if h.changed_by else None
        history.append(ho)
    evidence = []
    for e in d.evidence:
        b = to_shape(e.bounds).bounds if e.bounds is not None else None
        evidence.append(
            EvidenceOut(
                kind=e.kind,
                url=f"/api/v1/files/{e.path}",
                width_px=e.width_px,
                height_px=e.height_px,
                bounds=[round(v, 6) for v in b] if b else None,
            )
        )
    s = d.scan
    return DetectionDetail(
        id=d.id,
        geometry=from_db(d.geom) or {},
        properties=_props(d),
        parcel={
            "id": str(d.parcel.id),
            "name": d.parcel.name,
            "category": d.parcel.category,
            "area_m2": d.parcel.area_m2,
        },
        scan=ScanSummary(
            id=s.id,
            baseline_start=s.baseline_start.isoformat(),
            baseline_end=s.baseline_end.isoformat(),
            current_start=s.current_start.isoformat(),
            current_end=s.current_end.isoformat(),
            algorithm_version=s.algorithm_version,
            created_at=s.created_at,
        ),
        evidence=evidence,
        history=list(reversed(history)),  # newest first
        allowed_transitions=allowed_transitions(d, user),
    )


# ---------- routes ----------


@router.get("", response_model=DetectionFeatureCollection)
def list_detections(
    _: ActiveUser,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
    scan_id: uuid.UUID | None = None,
    parcel_id: uuid.UUID | None = None,
    confidence: ConfidenceClass | None = None,
    status: DetectionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: Annotated[str | None, Query()] = None,
) -> DetectionFeatureCollection:
    f = Filters(scan_id, parcel_id, confidence, status, date_from, date_to, bbox)
    rows, total = DetectionRepository(db).list_page((page - 1) * page_size, page_size, **f.kwargs)
    return DetectionFeatureCollection(
        features=[_feature(d) for d in rows], total=total, page=page, page_size=page_size
    )


CSV_COLUMNS = [
    "id",
    "parcel_name",
    "parcel_id",
    "scan_id",
    "confidence",
    "score",
    "area_m2",
    "sources",
    "d_bui_mean",
    "d_ndvi_mean",
    "d_sigma_vv_mean_db",
    "sar_overlap",
    "status",
    "status_note",
    "reviewed_at",
    "created_at",
    "lon",
    "lat",
    "wkt",
]


def _csv_rows(rows: Iterator[Detection]) -> Iterator[str]:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")  # Excel-friendly
    w.writerow(CSV_COLUMNS)
    yield "\ufeff" + buf.getvalue()  # UTF-8 BOM so Excel reads m² etc. correctly
    for d in rows:
        buf.seek(0)
        buf.truncate()
        p = _props(d)
        w.writerow(
            [
                str(d.id),
                p.parcel_name,
                str(d.parcel_id),
                str(d.scan_id),
                d.confidence.value,
                f"{d.score:.3f}",
                f"{d.area_m2:.0f}",
                "+".join(p.sources),
                _num(d.d_bui_mean, 3),
                _num(d.d_ndvi_mean, 3),
                _num(d.d_sigma_vv_mean, 2),
                _num(d.sar_overlap, 2),
                d.status.value,
                d.status_note or "",
                d.reviewed_at.isoformat() if d.reviewed_at else "",
                d.created_at.isoformat(),
                p.centroid[0],
                p.centroid[1],
                to_shape(d.geom).wkt,
            ]
        )
        yield buf.getvalue()


def _num(v: float | None, nd: int) -> str:
    return "" if v is None else f"{v:.{nd}f}"


def _geojson_chunks(rows: Iterator[Detection]) -> Iterator[str]:
    yield (
        '{"type":"FeatureCollection","disclaimer":'
        + json.dumps(DetectionFeatureCollection.model_fields["disclaimer"].default)
        + ',"features":['
    )
    first = True
    for d in rows:
        feat = _feature(d).model_dump(mode="json")
        yield ("" if first else ",") + json.dumps(feat, separators=(",", ":"))
        first = False
    yield "]}"


@router.get("/export")
def export_detections(
    _: ActiveUser,
    db: DbDep,
    format: Literal["geojson", "csv"] = "geojson",
    scan_id: uuid.UUID | None = None,
    parcel_id: uuid.UUID | None = None,
    confidence: ConfidenceClass | None = None,
    status: DetectionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    """Filtered list as GeoJSON (QGIS) or CSV with WKT (Excel). Same filters as the list."""
    f = Filters(scan_id, parcel_id, confidence, status, date_from, date_to, bbox)
    repo = DetectionRepository(db)
    total = repo.count(**f.kwargs)
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"Export limited to {MAX_EXPORT_ROWS} detections; narrow the filters",
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    rows = repo.iter_all(**f.kwargs)
    if format == "csv":
        return StreamingResponse(
            _csv_rows(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="detections-{stamp}.csv"'},
        )
    return StreamingResponse(
        _geojson_chunks(rows),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="detections-{stamp}.geojson"'},
    )


def _get_or_404(db: DbDep, detection_id: uuid.UUID) -> Detection:
    d = DetectionRepository(db).get_full(detection_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Detection not found")
    return d


@router.get("/{detection_id}", response_model=DetectionDetail)
def get_detection(detection_id: uuid.UUID, user: ActiveUser, db: DbDep) -> DetectionDetail:
    return _detail(_get_or_404(db, detection_id), db, user)


@router.patch("/{detection_id}/status", response_model=DetectionDetail)
def change_status(
    detection_id: uuid.UUID, body: StatusChange, user: ReviewerUser, db: DbDep
) -> DetectionDetail:
    """Apply a review decision (appflow Flow D step 4–5). Every change writes an audit row."""
    d = _get_or_404(db, detection_id)
    if body.status == d.status:
        raise HTTPException(status_code=409, detail=f"Detection is already '{d.status.value}'")
    if body.status not in TRANSITIONS.get(d.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a detection from '{d.status.value}' to '{body.status.value}'",
        )
    if (d.status, body.status) in ADMIN_ONLY_TRANSITIONS and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Only an administrator can reopen a dismissal")
    note = (body.note or "").strip() or None
    if body.status == DetectionStatus.dismissed:
        if body.reason_code is None:
            raise HTTPException(status_code=422, detail="Dismissing requires a reason code")
        if body.reason_code == "other" and not note:
            raise HTTPException(status_code=422, detail="Reason 'other' needs a short note")
    try:
        DetectionRepository(db).set_status(
            d,
            body.status,
            user.id,
            note=note or (body.reason_code if body.status == DetectionStatus.dismissed else None),
            reason_code=body.reason_code if body.status == DetectionStatus.dismissed else None,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    db.commit()
    db.expire(d)  # app sessions keep state across commit; reload history/evidence fresh
    logger.info(
        "detection status changed",
        extra={"detection_id": str(d.id), "user_id": str(user.id), "step": body.status.value},
    )
    return _detail(_get_or_404(db, detection_id), db, user)
