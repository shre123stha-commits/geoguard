from fastapi import APIRouter
from sqlalchemy import Engine

from app.db.session import get_engine
from app.schemas.health import HealthResponse
from app.services.health import check_health

router = APIRouter(tags=["health"])


def _engine() -> Engine:
    return get_engine()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    report = check_health(_engine())
    return HealthResponse(
        status=report.status,
        database=report.database,
        postgis=report.postgis,
        migration=report.migration,
        detail=report.detail,
    )
