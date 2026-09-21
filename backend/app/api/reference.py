"""/reference-layers (Phase 9): protected / restricted zone boundaries for zone context.

Any signed-in user can list layers and fetch their geometry (map overlay); admins upload,
edit and delete. Layers are GeoJSON FeatureCollections in EPSG:4326 (Polygon/MultiPolygon);
convert shapefiles/KML with QGIS or mapshaper first (README explains how).
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ActiveUser, AdminUser, DbDep
from app.db.models import ReferenceLayer
from app.repositories.reference import ReferenceRepository
from app.schemas.reference import (
    ReferenceLayerCreate,
    ReferenceLayerCreateResult,
    ReferenceLayerList,
    ReferenceLayerOut,
    ReferenceLayerPatch,
)

router = APIRouter(prefix="/reference-layers", tags=["reference-layers"])
logger = logging.getLogger(__name__)


def _out(repo: ReferenceRepository, layer: ReferenceLayer) -> ReferenceLayerOut:
    return ReferenceLayerOut(
        id=layer.id,
        name=layer.name,
        kind=layer.kind,
        source=layer.source,
        source_date=layer.source_date,
        notes=layer.notes,
        buffer_m=layer.buffer_m,
        is_active=layer.is_active,
        feature_count=layer.feature_count,
        bounds=repo.bounds(layer),
        created_at=layer.created_at,
    )


def _get_or_404(db: DbDep, layer_id: uuid.UUID) -> ReferenceLayer:
    layer = ReferenceRepository(db).get(layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Reference layer not found")
    return layer


@router.get("", response_model=ReferenceLayerList)
def list_layers(_: ActiveUser, db: DbDep) -> ReferenceLayerList:
    repo = ReferenceRepository(db)
    return ReferenceLayerList(layers=[_out(repo, layer) for layer in repo.list_layers()])


@router.post("", response_model=ReferenceLayerCreateResult, status_code=201)
def create_layer(
    body: ReferenceLayerCreate, admin: AdminUser, db: DbDep
) -> ReferenceLayerCreateResult:
    repo = ReferenceRepository(db)
    layer, skipped = repo.create(
        name=body.name.strip(),
        kind=body.kind,
        features=[f.model_dump() for f in body.features],
        source=(body.source or "").strip() or None,
        source_date=body.source_date,
        notes=(body.notes or "").strip() or None,
        buffer_m=body.buffer_m,
        created_by=admin.id,
    )
    if layer.feature_count == 0:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="No valid polygons in the file: "
            + "; ".join(f"#{i + 1}: {why}" for i, why in skipped[:10]),
        )
    db.commit()
    db.refresh(layer)
    logger.info(
        "reference layer created",
        extra={
            "layer_id": str(layer.id),
            "features": layer.feature_count,
            "skipped": len(skipped),
            "user_id": str(admin.id),
        },
    )
    return ReferenceLayerCreateResult(
        layer=_out(repo, layer), skipped=[{"index": i, "reason": r} for i, r in skipped]
    )


@router.get("/{layer_id}", response_model=ReferenceLayerOut)
def get_layer(layer_id: uuid.UUID, _: ActiveUser, db: DbDep) -> ReferenceLayerOut:
    return _out(ReferenceRepository(db), _get_or_404(db, layer_id))


@router.get("/{layer_id}/features")
def layer_features(
    layer_id: uuid.UUID,
    _: ActiveUser,
    db: DbDep,
    simplify: Annotated[float, Query(ge=0, le=0.01)] = 0.0,
) -> dict[str, Any]:
    """GeoJSON FeatureCollection for the map overlay (`simplify` in degrees; 0.0001 ≈ 10 m)."""
    layer = _get_or_404(db, layer_id)
    return ReferenceRepository(db).features_geojson(layer, simplify)


@router.patch("/{layer_id}", response_model=ReferenceLayerOut)
def patch_layer(
    layer_id: uuid.UUID, body: ReferenceLayerPatch, admin: AdminUser, db: DbDep
) -> ReferenceLayerOut:
    layer = _get_or_404(db, layer_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(layer, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(layer)
    return _out(ReferenceRepository(db), layer)


@router.delete("/{layer_id}", status_code=204)
def delete_layer(layer_id: uuid.UUID, admin: AdminUser, db: DbDep) -> None:
    layer = _get_or_404(db, layer_id)
    ReferenceRepository(db).delete(layer)
    db.commit()
    logger.info(
        "reference layer deleted", extra={"layer_id": str(layer_id), "user_id": str(admin.id)}
    )
