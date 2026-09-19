"""FastAPI application factory (task 0.5; routers added per phase)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.errors import register_error_handlers
from app.api.health import router as health_router
from app.api.parcels import router as parcels_router
from app.api.prototype import router as prototype_router
from app.api.users import router as users_router
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.services.prototype import PrototypeStore
from app.services.throttle import LoginThrottle

API_PREFIX = "/api/v1"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = PrototypeStore(settings.data_dir)
    store.load()
    app.state.prototype_store = store
    if settings.jwt_secret_is_placeholder and settings.environment == "prod":
        raise RuntimeError("JWT_SECRET must be set in production")
    if settings.jwt_secret_is_placeholder:
        logger.warning("JWT_SECRET is a placeholder; logins are insecure until it is set")
    logger.info("app started", extra={"step": "startup"})
    yield
    logger.info("app stopped", extra={"step": "shutdown"})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.login_throttle = LoginThrottle()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    # /health is public and unversioned (techspec §6); also mounted under the API prefix.
    app.include_router(health_router)
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(users_router, prefix=API_PREFIX)
    app.include_router(parcels_router, prefix=API_PREFIX)
    # detections/scans stay file-backed until Phases 4–5 replace them on the same paths
    app.include_router(prototype_router, prefix=API_PREFIX)
    return app


app = create_app()
