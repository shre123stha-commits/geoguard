"""Reference layer DTOs (Phase 9)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReferenceKind = Literal["wetland", "water_body", "forest", "coastal", "land_use", "custom"]
MAX_FEATURES_PER_LAYER = 5000

ZONE_DISCLAIMER = (
    "Zone context compares the detection footprint with a reference boundary you uploaded. "
    "Boundaries can be outdated or offset by tens of metres; permissions and exemptions are not "
    "known to this tool. Treat a zone hit as a reason to check first, not as a finding."
)


class ReferenceFeatureIn(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class ReferenceLayerCreate(BaseModel):
    """POST /reference-layers: a GeoJSON FeatureCollection plus metadata."""

    name: str = Field(min_length=1, max_length=200)
    kind: ReferenceKind = "custom"
    source: str | None = Field(default=None, max_length=300)
    source_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    buffer_m: int = Field(default=0, ge=0, le=5000)
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ReferenceFeatureIn] = Field(min_length=1, max_length=MAX_FEATURES_PER_LAYER)


class ReferenceLayerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: ReferenceKind | None = None
    source: str | None = Field(default=None, max_length=300)
    source_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    buffer_m: int | None = Field(default=None, ge=0, le=5000)
    is_active: bool | None = None


class ReferenceLayerOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    source: str | None
    source_date: date | None
    notes: str | None
    buffer_m: int
    is_active: bool
    feature_count: int
    bounds: list[float] | None
    created_at: datetime


class ReferenceLayerCreateResult(BaseModel):
    layer: ReferenceLayerOut
    skipped: list[dict[str, Any]]


class ReferenceLayerList(BaseModel):
    layers: list[ReferenceLayerOut]
    disclaimer: str = ZONE_DISCLAIMER


class ZoneHitOut(BaseModel):
    layer_id: uuid.UUID
    layer_name: str
    kind: str
    feature_name: str | None
    relation: Literal["inside", "partly_inside", "within_buffer"]
    inside_pct: int
    distance_m: int
    buffer_m: int
    source: str | None
    source_date: date | None
    text: str


class ZoneContextOut(BaseModel):
    priority: Literal["critical", "high", "elevated", "normal"]
    summary: str
    hits: list[ZoneHitOut]
