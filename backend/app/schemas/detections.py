"""Detection DTOs (techspec §6; appflow Flow D). Geometry is GeoJSON in EPSG:4326."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import ConfidenceClass, DetectionStatus, EvidenceKind
from app.schemas.reference import ZoneContextOut

DISCLAIMER = (
    "Satellite detection is a screening aid. Minimum reliable detection size is about 400 m² "
    "(Sentinel 10 m pixels). Verify on the ground before acting."
)

# Reason codes offered when dismissing (schema 05 §4.7 comment; appflow Flow D step 4).
REASON_CODES = (
    "bare_soil",
    "cloud_shadow",
    "seasonal",
    "water_level",
    "existing_structure",
    "other",
)
ReasonCode = Literal[
    "bare_soil", "cloud_shadow", "seasonal", "water_level", "existing_structure", "other"
]

# Allowed transitions (appflow §"Detection status"). Reopening dismissed → new is admin-only.
TRANSITIONS: dict[DetectionStatus, set[DetectionStatus]] = {
    DetectionStatus.new: {
        DetectionStatus.confirmed,
        DetectionStatus.dismissed,
        DetectionStatus.field_visit,
    },
    DetectionStatus.field_visit: {DetectionStatus.confirmed, DetectionStatus.dismissed},
    DetectionStatus.confirmed: {DetectionStatus.dismissed},
    DetectionStatus.dismissed: {DetectionStatus.new},
}
REASON_CODES = ReasonCode.__args__  # type: ignore[attr-defined]
ADMIN_ONLY_TRANSITIONS = {(DetectionStatus.dismissed, DetectionStatus.new)}


class DetectionMetrics(BaseModel):
    d_bui_mean: float | None
    d_ndvi_mean: float | None
    d_sigma_vv_mean_db: float | None
    sar_overlap: float | None


class DetectionProps(BaseModel):
    """Feature properties for the list; kept small so a few hundred features stay light."""

    id: uuid.UUID
    scan_id: uuid.UUID
    parcel_id: uuid.UUID
    parcel_name: str
    confidence: ConfidenceClass
    score: float
    area_m2: float
    sources: list[str]
    metrics: DetectionMetrics
    status: DetectionStatus
    status_note: str | None
    reviewed_at: datetime | None
    matches_detection: uuid.UUID | None
    created_at: datetime
    centroid: list[float]  # [lon, lat]
    zone: ZoneContextOut | None = None  # Phase 9: priority + reference-zone hits
    persistence: int = 1  # Phase 9.2: number of consecutive scans that flagged this site


class DetectionFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: uuid.UUID
    geometry: dict[str, Any]
    properties: DetectionProps


class DetectionFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[DetectionFeature]
    total: int
    page: int
    page_size: int
    disclaimer: str = DISCLAIMER


class EvidenceOut(BaseModel):
    kind: EvidenceKind
    url: str  # protected /api/v1/files/... route (5.3)
    width_px: int | None
    height_px: int | None
    bounds: list[float] | None  # [minx, miny, maxx, maxy] WGS84
    meta: dict[str, Any] = {}  # field photos: lon/lat/distance_m/position_source/note


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: DetectionStatus | None
    to_status: DetectionStatus
    note: str | None
    reason_code: str | None
    changed_by: uuid.UUID | None
    changed_by_name: str | None = None
    changed_at: datetime


class ScanSummary(BaseModel):
    id: uuid.UUID
    baseline_start: str
    baseline_end: str
    current_start: str
    current_end: str
    algorithm_version: str
    created_at: datetime


class ReportOut(BaseModel):
    id: uuid.UUID
    url: str
    generated_at: datetime
    generated_by_name: str | None = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    recipient: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class DetectionDetail(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: uuid.UUID
    geometry: dict[str, Any]
    properties: DetectionProps
    parcel: dict[str, Any]  # id, name, category, area_m2
    scan: ScanSummary
    evidence: list[EvidenceOut]
    history: list[HistoryOut]
    allowed_transitions: list[DetectionStatus]
    reports: list[ReportOut] = []
    alerts: list[AlertOut] = []
    disclaimer: str = DISCLAIMER


class StatusChange(BaseModel):
    status: DetectionStatus
    note: str | None = Field(default=None, max_length=2000)
    reason_code: ReasonCode | None = None
