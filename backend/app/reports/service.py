"""Build and store a detection report (task 7.1). Files go to DATA_DIR/reports/<detection>/."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.db.models import Detection, Report, User
from app.reports.pdf import ReportData, build_report
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)


def generate_report(db: Session, data_dir: Path, d: Detection, user: User) -> Report:
    c = to_shape(d.centroid)
    names = UserRepository(db).names_for([h.changed_by for h in d.history if h.changed_by])
    sources = [s for s, on in (("optical", d.optical_detected), ("radar", d.radar_detected)) if on]
    data = ReportData(
        detection_id=str(d.id),
        parcel_name=d.parcel.name,
        parcel_category=d.parcel.category,
        confidence=d.confidence.value,
        score=d.score,
        status=d.status.value,
        area_m2=d.area_m2,
        centroid_lon=c.x,
        centroid_lat=c.y,
        sources=sources,
        baseline=(d.scan.baseline_start.isoformat(), d.scan.baseline_end.isoformat()),
        current=(d.scan.current_start.isoformat(), d.scan.current_end.isoformat()),
        algorithm_version=d.scan.algorithm_version,
        detected_at=d.created_at,
        metrics={
            "d_bui_mean": d.d_bui_mean,
            "d_ndvi_mean": d.d_ndvi_mean,
            "d_sigma_vv_mean_db": d.d_sigma_vv_mean,
            "sar_overlap": d.sar_overlap,
        },
        history=[
            (
                h.changed_at,
                h.from_status.value if h.from_status else "—",
                h.to_status.value,
                names.get(h.changed_by) if h.changed_by else None,
                h.note,
            )
            for h in reversed(d.history)
        ],
        evidence={e.kind.value: data_dir / e.path for e in d.evidence},
        generated_by=user.full_name,
    )
    now = datetime.now(UTC)
    pdf = build_report(data, now)
    rel = Path("reports") / str(d.id) / f"report-{now.strftime('%Y%m%d-%H%M%S')}.pdf"
    out = data_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    rep = Report(id=uuid.uuid4(), detection_id=d.id, path=rel.as_posix(), generated_by=user.id)
    db.add(rep)
    db.flush()
    logger.info(
        "report generated",
        extra={"detection_id": str(d.id), "user_id": str(user.id), "step": "report"},
    )
    return rep
