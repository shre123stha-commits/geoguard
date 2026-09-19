"""Health service: liveness plus DB/PostGIS connectivity check (techspec §6, §9)."""

import logging
from dataclasses import dataclass

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthReport:
    status: str  # "ok" | "degraded"
    database: str  # "ok" | "error"
    postgis: str | None  # PostGIS version string when reachable
    migration: str | None  # alembic revision (None until Phase 2)
    detail: str | None = None


def check_health(engine: Engine) -> HealthReport:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            postgis = conn.execute(text("SELECT PostGIS_Version()")).scalar_one_or_none()
            revision = _alembic_revision(conn)
    except SQLAlchemyError as exc:  # noqa: BLE001 - we want the DB error class only
        logger.warning("health db check failed: %s", exc.__class__.__name__)
        return HealthReport(
            status="degraded",
            database="error",
            postgis=None,
            migration=None,
            detail="database unreachable",
        )
    return HealthReport(
        status="ok",
        database="ok",
        postgis=str(postgis) if postgis else None,
        migration=revision,
    )


def _alembic_revision(conn: object) -> str | None:
    from sqlalchemy import Connection

    assert isinstance(conn, Connection)
    try:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        conn.rollback()
        return None
