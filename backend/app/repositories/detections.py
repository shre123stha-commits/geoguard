import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import Select, case, cast, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.db.enums import ConfidenceClass, DetectionStatus, EvidenceKind
from app.db.models import Detection, DetectionStatusHistory, EvidenceFile, Parcel, Scan
from app.repositories.base import geojson_to_multipolygon, to_db


class DetectionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, detection_id: uuid.UUID) -> Detection | None:
        return self.db.get(Detection, detection_id)

    def create(
        self,
        scan: Scan,
        parcel: Parcel,
        geometry: dict[str, Any],
        area_m2: float,
        confidence: ConfidenceClass,
        score: float,
        optical_detected: bool,
        radar_detected: bool,
        d_bui_mean: float | None = None,
        d_ndvi_mean: float | None = None,
        d_sigma_vv_mean: float | None = None,
        sar_overlap: float | None = None,
    ) -> Detection:
        geom = geojson_to_multipolygon(geometry)
        det = Detection(
            scan_id=scan.id,
            parcel_id=parcel.id,
            geom=to_db(geom),
            centroid=to_db(geom.centroid),
            area_m2=area_m2,
            confidence=confidence,
            score=score,
            optical_detected=optical_detected,
            radar_detected=radar_detected,
            d_bui_mean=d_bui_mean,
            d_ndvi_mean=d_ndvi_mean,
            d_sigma_vv_mean=d_sigma_vv_mean,
            sar_overlap=sar_overlap,
        )
        self.db.add(det)
        self.db.flush()
        return det

    def query(
        self,
        scan_id: uuid.UUID | None = None,
        parcel_id: uuid.UUID | None = None,
        confidence: ConfidenceClass | None = None,
        status: DetectionStatus | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        in_zone: bool | None = None,
    ) -> Select[tuple[Detection]]:
        # Default sort per appflow Flow D: confidence desc, area desc (newest scan first).
        conf_rank = case(
            (Detection.confidence == ConfidenceClass.high, 0),
            (Detection.confidence == ConfidenceClass.medium, 1),
            else_=2,
        )
        q = select(Detection).order_by(
            Detection.created_at.desc(), conf_rank, Detection.area_m2.desc(), Detection.id
        )
        if scan_id:
            q = q.where(Detection.scan_id == scan_id)
        if parcel_id:
            q = q.where(Detection.parcel_id == parcel_id)
        if confidence:
            q = q.where(Detection.confidence == confidence)
        if status:
            q = q.where(Detection.status == status)
        if since:
            q = q.where(Detection.created_at >= since)
        if until:
            q = q.where(Detection.created_at < until)
        if bbox:
            env = func.ST_MakeEnvelope(*bbox, 4326)
            q = q.where(Detection.geom.op("&&")(env))
        if in_zone is not None:
            from app.repositories.reference import ReferenceRepository

            sub = ReferenceRepository(self.db).detection_ids_in_zones()
            q = q.where(Detection.id.in_(sub) if in_zone else Detection.id.not_in(sub))
        return q

    def list_all(self, limit: int = 500, offset: int = 0, **filters: Any) -> list[Detection]:
        return list(self.db.scalars(self.query(**filters).limit(limit).offset(offset)))

    def list_page(self, offset: int, limit: int, **filters: Any) -> tuple[list[Detection], int]:
        q = self.query(**filters).options(selectinload(Detection.parcel))
        rows = list(self.db.scalars(q.offset(offset).limit(limit)))
        return rows, self.count(**filters)

    def iter_all(self, batch: int = 500, **filters: Any) -> Iterator[Detection]:
        """Stream the filtered list for exports without loading everything at once."""
        q = self.query(**filters).options(selectinload(Detection.parcel))
        offset = 0
        while True:
            rows = list(self.db.scalars(q.offset(offset).limit(batch)))
            if not rows:
                return
            yield from rows
            offset += batch

    def get_full(self, detection_id: uuid.UUID) -> Detection | None:
        q = (
            select(Detection)
            .where(Detection.id == detection_id)
            .options(
                selectinload(Detection.parcel),
                selectinload(Detection.scan),
                selectinload(Detection.history),
                selectinload(Detection.evidence),
            )
        )
        return self.db.scalar(q)

    def count(self, **filters: Any) -> int:
        sub = self.query(**filters).order_by(None).subquery()
        return int(self.db.scalar(select(func.count()).select_from(sub)) or 0)

    def set_status(
        self,
        det: Detection,
        to_status: DetectionStatus,
        changed_by: uuid.UUID | None,
        note: str | None = None,
        reason_code: str | None = None,
    ) -> DetectionStatusHistory:
        if to_status == DetectionStatus.dismissed and not (note and note.strip()):
            raise ValueError("dismissals require a reason")
        hist = DetectionStatusHistory(
            detection_id=det.id,
            from_status=det.status,
            to_status=to_status,
            note=note,
            reason_code=reason_code,
            changed_by=changed_by,
        )
        det.status = to_status
        det.status_note = note
        det.reviewed_by = changed_by
        det.reviewed_at = datetime.now(UTC)
        self.db.add(hist)
        self.db.flush()
        return hist

    def add_evidence(
        self,
        det: Detection,
        kind: EvidenceKind,
        path: str,
        width_px: int | None = None,
        height_px: int | None = None,
        bounds: dict[str, Any] | None = None,
    ) -> EvidenceFile:
        from shapely.geometry import shape

        ev = EvidenceFile(
            detection_id=det.id,
            kind=kind,
            path=path,
            width_px=width_px,
            height_px=height_px,
            bounds=to_db(shape(bounds)) if bounds else None,
        )
        self.db.add(ev)
        self.db.flush()
        return ev

    def evidence_for(self, det: Detection) -> list[EvidenceFile]:
        return list(
            self.db.scalars(select(EvidenceFile).where(EvidenceFile.detection_id == det.id))
        )

    def count_by_scan(self, scan_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not scan_ids:
            return {}
        rows = self.db.execute(
            select(Detection.scan_id, func.count())
            .where(Detection.scan_id.in_(scan_ids))
            .group_by(Detection.scan_id)
        )
        return {sid: int(n) for sid, n in rows}

    def persistence_counts(self, detection_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """How many scans (including this one) have flagged the same site, following the
        `matches_detection` chain backwards. One recursive query for a page of detections."""
        if not detection_ids:
            return {}
        sql = text(
            """
            WITH RECURSIVE chain AS (
                SELECT id AS root, id AS cur, matches_detection AS prev, 1 AS depth
                FROM detections WHERE id = ANY(:ids)
                UNION ALL
                SELECT c.root, d.id, d.matches_detection, c.depth + 1
                FROM chain c JOIN detections d ON d.id = c.prev
                WHERE c.depth < 50
            )
            SELECT root, max(depth) FROM chain GROUP BY root
            """
        )
        rows = self.db.execute(sql, {"ids": list(detection_ids)})
        out = {d: 1 for d in detection_ids}
        for root, depth in rows:
            out[root] = int(depth)
        return out

    def reviewed_samples(self) -> list[Detection]:
        """Confirmed / dismissed detections with their measurements — the free labels that
        reviewing produces (used by the threshold insight)."""
        q = (
            select(Detection)
            .where(Detection.status.in_([DetectionStatus.confirmed, DetectionStatus.dismissed]))
            .options(selectinload(Detection.history))
        )
        return list(self.db.scalars(q))

    def find_previous_match(self, det: Detection) -> Detection | None:
        """Same site seen in an earlier scan: overlap > 50 % of the smaller area (schema 05 §6)."""
        inter = func.ST_Area(cast(func.ST_Intersection(Detection.geom, det.geom), Geography))
        # Candidates come from other scans created no later than this one (`<=`: rows written in
        # the same transaction share now()); the detection itself is excluded via scan_id.
        q = (
            select(Detection)
            .join(Scan, Scan.id == Detection.scan_id)
            .where(Detection.scan_id != det.scan_id)
            .where(Detection.created_at <= det.created_at)
            .where(func.ST_Intersects(Detection.geom, det.geom))
            .where(inter > 0.5 * func.least(Detection.area_m2, det.area_m2))
            .order_by(Scan.created_at.desc(), Detection.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(q)
