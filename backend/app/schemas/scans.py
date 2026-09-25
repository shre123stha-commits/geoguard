import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import PeriodType, ScanStatus, SensorType


class ScanParamsIn(BaseModel):
    """Tunable thresholds (techspec §5.2). Defaults match the evaluated baseline."""

    t_bui: float = Field(default=0.15, ge=0.0, le=1.0)
    t_ndvi_drop: float = Field(default=0.10, ge=0.0, le=1.0)
    t_sar_db: float = Field(default=2.5, ge=0.0, le=10.0)
    overlap: float = Field(default=0.3, ge=0.0, le=1.0)
    min_area_m2: float = Field(default=400.0, ge=100.0, le=100_000.0)
    cloud_cover_max: int = Field(default=30, ge=0, le=100)
    # "two_window": compare two composites (v1). "seasonal": fit a seasonal model to the
    # baseline months and flag persistent anomalies in the current months (design note §5).
    mode: Literal["two_window", "seasonal"] = "two_window"
    persist: int = Field(default=3, ge=1, le=6)  # seasonal: consecutive anomalous months


class ScanCreate(BaseModel):
    parcel_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    baseline_start: date
    baseline_end: date
    current_start: date
    current_end: date
    params: ScanParamsIn = Field(default_factory=ScanParamsIn)

    @model_validator(mode="after")
    def _periods(self) -> "ScanCreate":
        if self.baseline_start > self.baseline_end:
            raise ValueError("baseline_start must be on or before baseline_end")
        if self.current_start > self.current_end:
            raise ValueError("current_start must be on or before current_end")
        if self.baseline_end >= self.current_start:
            raise ValueError("the baseline period must end before the current period starts")
        for a, b, name in (
            (self.baseline_start, self.baseline_end, "baseline"),
            (self.current_start, self.current_end, "current"),
        ):
            if (b - a).days < 4:
                raise ValueError(f"the {name} period must span at least 5 days")
            if (b - a).days > 366:
                raise ValueError(f"the {name} period must not exceed one year")
        if self.baseline_start < date(2015, 6, 23):
            raise ValueError("Sentinel-2 data starts on 2015-06-23")
        return self


class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor: SensorType
    period: PeriodType
    scene_id: str
    acquired_at: datetime
    cloud_cover: float | None
    orbit: str | None


class ScanParcelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ScanStatus
    step: str | None
    progress: int
    message: str | None
    error_code: str | None
    baseline_start: date
    baseline_end: date
    current_start: date
    current_end: date
    params: dict[str, Any]
    algorithm_version: str
    rerun_of: uuid.UUID | None
    schedule_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    detection_count: int = 0
    parcels: list[ScanParcelOut] = []


class ScanDetail(ScanOut):
    scenes: list[SceneOut] = []
    aoi: dict[str, Any] | None = None
