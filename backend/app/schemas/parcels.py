import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ParcelSource = Literal["upload", "drawn"]
MAX_FEATURES_PER_REQUEST = 500
MAX_VERTICES_PER_PARCEL = 5000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class ParcelProps(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    notes: str | None
    area_m2: float
    source: str
    source_ref: str | None
    created_at: datetime
    updated_at: datetime


class ParcelFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: uuid.UUID
    geometry: dict[str, Any]
    properties: ParcelProps


class ParcelFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ParcelFeature]
    total: int
    page: int
    page_size: int


class ParcelCreateFeature(BaseModel):
    """One incoming feature. `name`/`category` come from properties or the request defaults."""

    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class ParcelCreateRequest(BaseModel):
    """Body of POST /parcels: a GeoJSON FeatureCollection (uploaded or drawn) plus defaults.

    Per-feature `properties.name` / `properties.category` / `properties.notes` win over the
    request-level defaults. Invalid features are skipped and reported (appflow Flow B step 5).
    """

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ParcelCreateFeature] = Field(min_length=1, max_length=MAX_FEATURES_PER_REQUEST)
    source: ParcelSource = "upload"
    source_ref: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class ParcelSkipped(BaseModel):
    index: int
    name: str | None
    reason: str


class ParcelCreateResult(BaseModel):
    created: list[ParcelFeature]
    skipped: list[ParcelSkipped]


class ParcelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    # Geometry redraw is only allowed for drawn parcels (appflow Flow B step 9).
    geometry: dict[str, Any] | None = None


class ParcelDeleteResult(BaseModel):
    deleted: uuid.UUID
    cascade: bool
    scans_removed: int
    detections_removed: int
