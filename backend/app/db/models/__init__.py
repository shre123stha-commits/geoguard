"""SQLAlchemy 2 + GeoAlchemy2 models — one class per table in docs/05-schema.md §4.

Enum types are created with `create_type=False`: the migrations own them (0001).
"""

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, REAL
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk
from app.db.enums import (
    AlertStatus,
    ConfidenceClass,
    DetectionStatus,
    EvidenceKind,
    PeriodType,
    ScanStatus,
    SensorType,
    UserRole,
)


def _enum(e: type, name: str) -> Enum:
    return Enum(e, name=name, create_type=False, values_callable=lambda x: [m.value for m in x])


def _uuid_fk(target: str, ondelete: str, nullable: bool = True) -> Any:
    return mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


# 4.1
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), nullable=False, server_default=UserRole.officer.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    telegram_chat_id: Mapped[str | None] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


# 4.2
class Parcel(Base):
    __tablename__ = "parcels"
    __table_args__ = (
        CheckConstraint("source IN ('upload','drawn')", name="parcels_source_check"),
        CheckConstraint("ST_IsValid(geom)", name="parcels_valid_geom"),
        Index("idx_parcels_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="upload")
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    detections: Mapped[list["Detection"]] = relationship(back_populates="parcel")


# 4.3
class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint("progress BETWEEN 0 AND 100", name="scans_progress_check"),
        CheckConstraint(
            "baseline_start <= baseline_end AND current_start <= current_end "
            "AND baseline_end < current_start",
            name="scans_periods_ok",
        ),
        Index("idx_scans_status_created", "status", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    status: Mapped[ScanStatus] = mapped_column(
        _enum(ScanStatus, "scan_status"), nullable=False, server_default=ScanStatus.queued.value
    )
    step: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    current_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_end: Mapped[date] = mapped_column(Date, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    aoi_geom: Mapped[Any | None] = mapped_column(
        Geometry("POLYGON", srid=4326, spatial_index=False)
    )
    rerun_of: Mapped[uuid.UUID | None] = _uuid_fk("scans.id", "SET NULL")
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scan_schedules.id", ondelete="SET NULL", name="scans_schedule_fk"),
    )
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    created_at: Mapped[datetime] = created_at_col()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    parcels: Mapped[list[Parcel]] = relationship(secondary="scan_parcels")
    scenes: Mapped[list["ScanScene"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    detections: Mapped[list["Detection"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


# 4.4
class ScanParcel(Base):
    __tablename__ = "scan_parcels"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    parcel_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("parcels.id", ondelete="RESTRICT"), primary_key=True
    )


# 4.5
class ScanScene(Base):
    __tablename__ = "scan_scenes"
    __table_args__ = (
        UniqueConstraint("scan_id", "sensor", "period", "scene_id", name="scan_scenes_unique"),
        Index("idx_scan_scenes_scan", "scan_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scan_id: Mapped[uuid.UUID] = _uuid_fk("scans.id", "CASCADE", nullable=False)
    sensor: Mapped[SensorType] = mapped_column(_enum(SensorType, "sensor_type"), nullable=False)
    period: Mapped[PeriodType] = mapped_column(_enum(PeriodType, "period_type"), nullable=False)
    scene_id: Mapped[str] = mapped_column(Text, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cloud_cover: Mapped[float | None] = mapped_column(REAL)
    orbit: Mapped[str | None] = mapped_column(Text)
    footprint: Mapped[Any | None] = mapped_column(
        Geometry("POLYGON", srid=4326, spatial_index=False)
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    scan: Mapped[Scan] = relationship(back_populates="scenes")


# 4.6
class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        CheckConstraint("area_m2 > 0", name="detections_area_check"),
        CheckConstraint("score BETWEEN 0 AND 1", name="detections_score_check"),
        CheckConstraint(
            "sar_overlap IS NULL OR sar_overlap BETWEEN 0 AND 1", name="detections_overlap_check"
        ),
        Index("idx_detections_geom", "geom", postgresql_using="gist"),
        Index("idx_detections_centroid", "centroid", postgresql_using="gist"),
        Index("idx_detections_scan", "scan_id"),
        Index("idx_detections_parcel", "parcel_id"),
        Index("idx_detections_filter", "status", "confidence", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scan_id: Mapped[uuid.UUID] = _uuid_fk("scans.id", "CASCADE", nullable=False)
    parcel_id: Mapped[uuid.UUID] = _uuid_fk("parcels.id", "RESTRICT", nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )
    centroid: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    )
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[ConfidenceClass] = mapped_column(
        _enum(ConfidenceClass, "confidence_class"), nullable=False
    )
    score: Mapped[float] = mapped_column(REAL, nullable=False)
    optical_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    radar_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    d_bui_mean: Mapped[float | None] = mapped_column(REAL)
    d_ndvi_mean: Mapped[float | None] = mapped_column(REAL)
    d_sigma_vv_mean: Mapped[float | None] = mapped_column(REAL)
    sar_overlap: Mapped[float | None] = mapped_column(REAL)
    status: Mapped[DetectionStatus] = mapped_column(
        _enum(DetectionStatus, "detection_status"),
        nullable=False,
        server_default=DetectionStatus.new.value,
    )
    status_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matches_detection: Mapped[uuid.UUID | None] = _uuid_fk("detections.id", "SET NULL")
    created_at: Mapped[datetime] = created_at_col()

    scan: Mapped[Scan] = relationship(back_populates="detections")
    parcel: Mapped[Parcel] = relationship(back_populates="detections")
    history: Mapped[list["DetectionStatusHistory"]] = relationship(
        back_populates="detection",
        cascade="all, delete-orphan",
        order_by="DetectionStatusHistory.changed_at",
    )
    evidence: Mapped[list["EvidenceFile"]] = relationship(cascade="all, delete-orphan")


# 4.7
class DetectionStatusHistory(Base):
    __tablename__ = "detection_status_history"
    __table_args__ = (Index("idx_dsh_detection", "detection_id", text("changed_at DESC")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    detection_id: Mapped[uuid.UUID] = _uuid_fk("detections.id", "CASCADE", nullable=False)
    from_status: Mapped[DetectionStatus | None] = mapped_column(
        _enum(DetectionStatus, "detection_status")
    )
    to_status: Mapped[DetectionStatus] = mapped_column(
        _enum(DetectionStatus, "detection_status"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    changed_at: Mapped[datetime] = created_at_col()

    detection: Mapped[Detection] = relationship(back_populates="history")


# 4.8
class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    __table_args__ = (UniqueConstraint("detection_id", "kind", name="evidence_files_unique"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    detection_id: Mapped[uuid.UUID] = _uuid_fk("detections.id", "CASCADE", nullable=False)
    kind: Mapped[EvidenceKind] = mapped_column(_enum(EvidenceKind, "evidence_kind"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    bounds: Mapped[Any | None] = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_col()


# 4.9
class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("idx_reports_detection", "detection_id", text("generated_at DESC")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    detection_id: Mapped[uuid.UUID] = _uuid_fk("detections.id", "CASCADE", nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    generated_at: Mapped[datetime] = created_at_col()


# 4.10
class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("idx_alerts_detection", "detection_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    detection_id: Mapped[uuid.UUID] = _uuid_fk("detections.id", "CASCADE", nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, server_default="console")
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        _enum(AlertStatus, "alert_status"), nullable=False, server_default=AlertStatus.pending.value
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# 4.11
class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    updated_at: Mapped[datetime] = updated_at_col()


# 4.12
class ScanSchedule(Base):
    __tablename__ = "scan_schedules"
    __table_args__ = (
        CheckConstraint(
            "current_window_days BETWEEN 5 AND 120", name="scan_schedules_window_check"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    cron: Mapped[str] = mapped_column(Text, nullable=False)
    current_window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    baseline_rule: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    created_at: Mapped[datetime] = created_at_col()

    parcels: Mapped[list[Parcel]] = relationship(secondary="schedule_parcels")


class ScheduleParcel(Base):
    __tablename__ = "schedule_parcels"

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scan_schedules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parcel_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True
    )


# Phase 9 — reference layers (protected / restricted zones used for zone context)
REFERENCE_KINDS = ("wetland", "water_body", "forest", "coastal", "land_use", "custom")


class ReferenceLayer(Base):
    __tablename__ = "reference_layers"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('wetland','water_body','forest','coastal','land_use','custom')",
            name="reference_layers_kind_check",
        ),
        CheckConstraint("buffer_m BETWEEN 0 AND 5000", name="reference_layers_buffer_check"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    source_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    buffer_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", "SET NULL")
    created_at: Mapped[datetime] = created_at_col()

    features: Mapped[list["ReferenceFeature"]] = relationship(
        back_populates="layer", cascade="all, delete-orphan", passive_deletes=True
    )


class ReferenceFeature(Base):
    __tablename__ = "reference_features"
    __table_args__ = (
        CheckConstraint("ST_IsValid(geom)", name="reference_features_valid_geom"),
        Index("idx_reference_features_geom", "geom", postgresql_using="gist"),
        Index("idx_reference_features_layer", "layer_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    layer_id: Mapped[uuid.UUID] = _uuid_fk("reference_layers.id", "CASCADE", nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    geom: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )

    layer: Mapped[ReferenceLayer] = relationship(back_populates="features")


# Phase 9.3 — per-parcel monthly time series
class ParcelTimeseries(Base):
    __tablename__ = "parcel_timeseries"

    parcel_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    built_frac: Mapped[float | None] = mapped_column(REAL)
    ndvi_mean: Mapped[float | None] = mapped_column(REAL)
    valid_frac: Mapped[float | None] = mapped_column(REAL)
    n_scenes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    t_bui: Mapped[float] = mapped_column(REAL, nullable=False)
    computed_at: Mapped[datetime] = created_at_col()


class TimelineJob(Base):
    __tablename__ = "timeline_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running','done','failed')", name="timeline_jobs_status"),
    )

    parcel_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    message: Mapped[str | None] = mapped_column(Text)
    months_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    months_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = [
    "Alert",
    "AppSetting",
    "Base",
    "Detection",
    "DetectionStatusHistory",
    "EvidenceFile",
    "Parcel",
    "ParcelTimeseries",
    "ReferenceFeature",
    "ReferenceLayer",
    "Report",
    "Scan",
    "ScanParcel",
    "ScanScene",
    "ScanSchedule",
    "ScheduleParcel",
    "TimelineJob",
    "User",
]
