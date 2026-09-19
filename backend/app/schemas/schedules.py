import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scans import ScanParamsIn, ScanParcelOut


class BaselineRule(BaseModel):
    mode: Literal["same_season_previous_year", "years_back", "fixed"] = "same_season_previous_year"
    window_days: int | None = Field(default=None, ge=5, le=120)
    years: int | None = Field(default=None, ge=1, le=8)
    baseline_start: str | None = None  # ISO date, mode=fixed
    baseline_end: str | None = None


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parcel_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    cron: str = Field(min_length=1, max_length=100, description="'weekly' | 'monthly' | crontab")
    current_window_days: int = Field(default=30, ge=5, le=120)
    baseline_rule: BaselineRule = Field(default_factory=BaselineRule)
    params: ScanParamsIn = Field(default_factory=ScanParamsIn)


class SchedulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parcel_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=500)
    cron: str | None = Field(default=None, min_length=1, max_length=100)
    current_window_days: int | None = Field(default=None, ge=5, le=120)
    baseline_rule: BaselineRule | None = None
    params: ScanParamsIn | None = None
    is_active: bool | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    cron: str
    current_window_days: int
    baseline_rule: dict[str, Any]
    params: dict[str, Any]
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    parcels: list[ScanParcelOut] = []
    last_scan_id: uuid.UUID | None = None
    last_scan_status: str | None = None
