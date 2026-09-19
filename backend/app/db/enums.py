"""Python enums mirrored as PostgreSQL ENUM types (schema 05 §3)."""

import enum


class UserRole(enum.StrEnum):
    admin = "admin"
    officer = "officer"


class ScanStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class DetectionStatus(enum.StrEnum):
    new = "new"
    confirmed = "confirmed"
    dismissed = "dismissed"
    field_visit = "field_visit"


class ConfidenceClass(enum.StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class SensorType(enum.StrEnum):
    sentinel1 = "sentinel1"
    sentinel2 = "sentinel2"


class PeriodType(enum.StrEnum):
    baseline = "baseline"
    current = "current"


class EvidenceKind(enum.StrEnum):
    before_rgb = "before_rgb"
    after_rgb = "after_rgb"
    change_map = "change_map"
    overview = "overview"


class AlertStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
