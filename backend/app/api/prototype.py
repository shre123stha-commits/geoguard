"""Prototype endpoints (Phase 1 slice, tracker D42). Same paths as techspec §6 so the frontend
does not change when PostGIS-backed routers replace this module in Phase 2/3."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.prototype import DISCLAIMER, PrototypeStore

router = APIRouter(tags=["prototype"])


def _store(request: Request) -> PrototypeStore:
    store: PrototypeStore = request.app.state.prototype_store
    return store


class ScanCreate(BaseModel):
    t_bui: float = Field(default=0.15, ge=0.0, le=1.0)
    t_sar_db: float = Field(default=2.5, ge=0.0, le=10.0)
    overlap: float = Field(default=0.3, ge=0.0, le=1.0)


class DetectionStatus(BaseModel):
    status: Literal["new", "confirmed", "dismissed", "field_visit"]
    note: str = ""


@router.get("/parcels")
def list_parcels(request: Request) -> dict[str, Any]:
    return _store(request).parcel_feature_collection()


@router.get("/detections")
def list_detections(
    request: Request,
    confidence: Literal["high", "medium", "low"] | None = None,
    parcel_id: int | None = None,
) -> dict[str, Any]:
    fc = _store(request).detection_feature_collection(confidence, parcel_id)
    fc["disclaimer"] = DISCLAIMER
    return fc


@router.get("/detections/{detection_id}")
def get_detection(request: Request, detection_id: int) -> dict[str, Any]:
    for d in _store(request).detections:
        if d["id"] == detection_id:
            return {**d, "disclaimer": DISCLAIMER}
    raise HTTPException(status_code=404, detail="Detection not found")


@router.post("/detections/{detection_id}/status")
def set_status(request: Request, detection_id: int, body: DetectionStatus) -> dict[str, Any]:
    if body.status == "dismissed" and not body.note.strip():
        raise HTTPException(status_code=400, detail="Dismissals require a reason")
    for d in _store(request).detections:
        if d["id"] == detection_id:
            d["status"] = body.status
            d["status_note"] = body.note
            return d
    raise HTTPException(status_code=404, detail="Detection not found")


@router.get("/scans")
def list_scans(request: Request) -> list[dict[str, Any]]:
    return _store(request).scans


@router.post("/scans", status_code=201)
def create_scan(request: Request, body: ScanCreate | None = None) -> dict[str, Any]:
    store = _store(request)
    if not store.composites_available():
        raise HTTPException(
            status_code=409,
            detail="No composites in data/composites. Run scripts/build_composites.py first.",
        )
    body = body or ScanCreate()
    return store.run_scan(body.t_bui, body.t_sar_db, body.overlap)
