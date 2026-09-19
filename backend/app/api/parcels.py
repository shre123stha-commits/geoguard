"""/parcels: GeoJSON in/out, EPSG:4326 (techspec §6). Task 3.2.

GET is open to any signed-in user; POST/PATCH/DELETE are admin-only.
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import ActiveUser, AdminUser, DbDep
from app.db.models import Parcel
from app.repositories import ParcelInUseError, ParcelRepository
from app.repositories.base import from_db, geojson_to_multipolygon, vertex_count
from app.schemas.common import PageParams, page_params
from app.schemas.parcels import (
    MAX_VERTICES_PER_PARCEL,
    ParcelCreateRequest,
    ParcelCreateResult,
    ParcelDeleteResult,
    ParcelFeature,
    ParcelFeatureCollection,
    ParcelPatch,
    ParcelProps,
    ParcelSkipped,
)

router = APIRouter(prefix="/parcels", tags=["parcels"])
logger = logging.getLogger(__name__)


def to_feature(p: Parcel) -> ParcelFeature:
    return ParcelFeature(
        id=p.id,
        geometry=from_db(p.geom) or {},
        properties=ParcelProps(
            id=p.id,
            name=p.name,
            category=p.category,
            notes=p.notes,
            area_m2=p.area_m2,
            source=p.source,
            source_ref=p.source_ref,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ),
    )


def _check_geometry(geometry: dict[str, Any]) -> None:
    """Raise ValueError with a user-readable reason (techspec §8: validity, CRS, vertex cap)."""
    g = geojson_to_multipolygon(geometry)
    n = vertex_count(g)
    if n > MAX_VERTICES_PER_PARCEL:
        raise ValueError(f"too many vertices ({n} > {MAX_VERTICES_PER_PARCEL}); simplify first")


def _clean_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


@router.get("", response_model=ParcelFeatureCollection)
def list_parcels(
    _: ActiveUser,
    db: DbDep,
    paging: Annotated[PageParams, Depends(page_params)],
    category: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> ParcelFeatureCollection:
    rows, total = ParcelRepository(db).list_page(paging.offset, paging.page_size, category, q)
    return ParcelFeatureCollection(
        features=[to_feature(p) for p in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post("", response_model=ParcelCreateResult, status_code=201)
def create_parcels(body: ParcelCreateRequest, admin: AdminUser, db: DbDep) -> ParcelCreateResult:
    repo = ParcelRepository(db)
    created: list[ParcelFeature] = []
    skipped: list[ParcelSkipped] = []
    for i, f in enumerate(body.features):
        props = f.properties or {}
        name = _clean_text(props.get("name"), 200) or body.name
        category = _clean_text(props.get("category"), 100) or body.category
        notes = _clean_text(props.get("notes"), 2000) or body.notes
        if not name:
            name = f"Parcel {i + 1}" if body.source == "drawn" else None
        if not name or not category:
            skipped.append(ParcelSkipped(index=i, name=name, reason="missing name or category"))
            continue
        try:
            _check_geometry(f.geometry)
            with db.begin_nested():
                p = repo.create(
                    name=name,
                    category=category,
                    geometry=f.geometry,
                    source=body.source,
                    notes=notes,
                    source_ref=body.source_ref,
                    created_by=admin.id,
                )
                if p.area_m2 < 1.0:
                    raise ValueError("area is below 1 m²")
        except ValueError as exc:
            skipped.append(ParcelSkipped(index=i, name=name, reason=str(exc)))
            continue
        created.append(to_feature(p))
    if not created:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="No valid parcels in the request: "
            + "; ".join(f"#{s.index + 1}: {s.reason}" for s in skipped[:10]),
        )
    db.commit()
    logger.info(
        "parcels created",
        extra={"count": len(created), "skipped": len(skipped), "user_id": str(admin.id)},
    )
    return ParcelCreateResult(created=created, skipped=skipped)


def _get_or_404(db: DbDep, parcel_id: uuid.UUID) -> Parcel:
    p = ParcelRepository(db).get(parcel_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return p


@router.get("/{parcel_id}", response_model=ParcelFeature)
def get_parcel(parcel_id: uuid.UUID, _: ActiveUser, db: DbDep) -> ParcelFeature:
    return to_feature(_get_or_404(db, parcel_id))


@router.patch("/{parcel_id}", response_model=ParcelFeature)
def patch_parcel(
    parcel_id: uuid.UUID, body: ParcelPatch, admin: AdminUser, db: DbDep
) -> ParcelFeature:
    repo = ParcelRepository(db)
    p = _get_or_404(db, parcel_id)
    if body.geometry is not None:
        if p.source != "drawn":
            raise HTTPException(
                status_code=409, detail="Geometry can only be redrawn for drawn parcels"
            )
        try:
            _check_geometry(body.geometry)
            repo.set_geometry(p, body.geometry)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    repo.update(p, name=body.name, category=body.category, notes=body.notes)
    db.commit()
    db.refresh(p)
    return to_feature(p)


@router.delete("/{parcel_id}", response_model=ParcelDeleteResult)
def delete_parcel(
    parcel_id: uuid.UUID,
    admin: AdminUser,
    db: DbDep,
    cascade: Annotated[bool, Query(description="Also remove scans/detections using it")] = False,
) -> ParcelDeleteResult:
    repo = ParcelRepository(db)
    p = _get_or_404(db, parcel_id)
    scans, dets = repo.usage(p.id)
    try:
        repo.delete(p, cascade=cascade)
    except ParcelInUseError:
        raise HTTPException(
            status_code=409,
            detail=f"Parcel is used by {scans} scan(s) and {dets} detection(s); "
            "repeat with ?cascade=true to remove them too",
        ) from None
    db.commit()
    logger.info(
        "parcel deleted",
        extra={"parcel_id": str(parcel_id), "cascade": cascade, "user_id": str(admin.id)},
    )
    return ParcelDeleteResult(
        deleted=parcel_id,
        cascade=cascade,
        scans_removed=scans if cascade else 0,
        detections_removed=dets if cascade else 0,
    )
