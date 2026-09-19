import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Detection, Parcel, ScanParcel
from app.repositories.base import geojson_to_multipolygon, to_db


class ParcelInUseError(Exception):
    """Raised when deleting a parcel that scans or detections still reference."""


class ParcelRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, parcel_id: uuid.UUID) -> Parcel | None:
        return self.db.get(Parcel, parcel_id)

    def list_all(self) -> list[Parcel]:
        return list(self.db.scalars(select(Parcel).order_by(Parcel.name)))

    def list_page(
        self, offset: int, limit: int, category: str | None = None, q: str | None = None
    ) -> tuple[list[Parcel], int]:
        stmt = select(Parcel)
        if category:
            stmt = stmt.where(Parcel.category == category)
        if q:
            stmt = stmt.where(Parcel.name.ilike(f"%{q}%"))
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.order_by(Parcel.name, Parcel.id).offset(offset).limit(limit))
        return list(rows), total

    def geodesic_area(self, geometry: dict[str, Any]) -> float:
        wkb = to_db(geojson_to_multipolygon(geometry))
        return float(self.db.scalar(select(func.ST_Area(func.ST_GeogFromWKB(wkb)))) or 0.0)

    def set_geometry(self, parcel: Parcel, geometry: dict[str, Any]) -> Parcel:
        parcel.geom = to_db(geojson_to_multipolygon(geometry))
        parcel.area_m2 = self.geodesic_area(geometry)
        self.db.flush()
        return parcel

    def create(
        self,
        name: str,
        category: str,
        geometry: dict[str, Any],
        source: str = "upload",
        notes: str | None = None,
        source_ref: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> Parcel:
        geom = geojson_to_multipolygon(geometry)
        wkb = to_db(geom)
        # geodesic area from PostGIS (schema 05 header: never in degrees)
        area = float(self.db.scalar(select(func.ST_Area(func.ST_GeogFromWKB(wkb)))) or 0.0)
        parcel = Parcel(
            name=name,
            category=category,
            notes=notes,
            geom=wkb,
            area_m2=area,
            source=source,
            source_ref=source_ref,
            created_by=created_by,
        )
        self.db.add(parcel)
        self.db.flush()
        return parcel

    def update(self, parcel: Parcel, **fields: Any) -> Parcel:
        for k in ("name", "category", "notes"):
            if k in fields and fields[k] is not None:
                setattr(parcel, k, fields[k])
        self.db.flush()
        return parcel

    def usage(self, parcel_id: uuid.UUID) -> tuple[int, int]:
        scans = int(
            self.db.scalar(
                select(func.count())
                .select_from(ScanParcel)
                .where(ScanParcel.parcel_id == parcel_id)
            )
            or 0
        )
        dets = int(
            self.db.scalar(
                select(func.count()).select_from(Detection).where(Detection.parcel_id == parcel_id)
            )
            or 0
        )
        return scans, dets

    def delete(self, parcel: Parcel, cascade: bool = False) -> None:
        scans, dets = self.usage(parcel.id)
        if (scans or dets) and not cascade:
            raise ParcelInUseError(f"parcel referenced by {scans} scans and {dets} detections")
        if cascade:
            # schema 05 §5: explicit admin cascade removes scans that include this parcel
            from app.db.models import Scan

            scan_ids = list(
                self.db.scalars(select(ScanParcel.scan_id).where(ScanParcel.parcel_id == parcel.id))
            )
            for s in self.db.scalars(select(Scan).where(Scan.id.in_(scan_ids))):
                self.db.delete(s)
            self.db.flush()
        self.db.delete(parcel)
        self.db.flush()

    def intersecting(self, geometry: dict[str, Any]) -> list[Parcel]:
        wkb = to_db(geojson_to_multipolygon(geometry))
        return list(self.db.scalars(select(Parcel).where(func.ST_Intersects(Parcel.geom, wkb))))
