"""File-backed detections (Phase 1 slice, tracker D42). Same paths as techspec §6 so the
frontend does not change when the PostGIS-backed router replaces it (Phase 5).
`/parcels` moved to `app/api/parcels.py` (Phase 3), `/scans` to `app/api/scans.py` (Phase 4)."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.prototype import DISCLAIMER, PrototypeStore

router = APIRouter(tags=["prototype"])


def _store(request: Request) -> PrototypeStore:
    store: PrototypeStore = request.app.state.prototype_store
    return store


class DetectionStatus(BaseModel):
    status: Literal["new", "confirmed", "dismissed", "field_visit"]
    note: str = ""


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
