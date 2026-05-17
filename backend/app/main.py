"""FastAPI application for VisionSafe 360 backend."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.stats import router as stats_router
from .api.routes.alerts import router as alerts_router
from .api.routes.analytics import router as analytics_router
from .api.routes.auth import router as auth_router
from .api.routes.cameras import router as cameras_router
from .api.routes.config_route import router as config_router
from .api.routes.edge_config import router as edge_config_router
from .api.routes.ergonomics import router as ergonomics_router
from .api.routes.health import router as health_router
from .api.routes.jobs import router as jobs_router
from .api.routes.media import router as media_router
from .api.routes.monitoring import router as monitoring_router
from .api.routes.notifications_route import router as notifications_router
from .api.routes.incidents import router as incidents_router
from .api.routes.ingest import router as ingest_router
from .api.routes.users import router as users_router
from .api.websocket.ws_handler import router as incidents_ws_router
from .api.websocket.ws_notifications import router as notifications_ws_router
from .api.websocket.ws_stream import router as stream_ws_router
from .config.database import Base, engine
from .config.settings import settings
from .seed import seed
from .services.schema_maintenance import ensure_alert_lifecycle_schema
from .utils.audit_logger import ensure_request_id, get_client_ip_from_request, get_audit_logger
from .utils.logging_config import setup_logging
from .utils.security import validate_security_config
from .utils.sentry_integration import init_sentry, set_sentry_context, sentry_enabled

app = FastAPI(
    title="VisionSafe 360 API",
    version="1.0.0",
    description="Backend API for VisionSafe 360 Safety Dashboard",
    docs_url="/docs",
    redoc_url="/redoc",
)

logger = logging.getLogger("visionsafe.backend")

# ── CORS — pulled from settings, not hardcoded ───────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging middleware ────────────────────────────────────────
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = ensure_request_id(request.headers.get("x-request-id"))
    client_ip = get_client_ip_from_request(request)
    request.state.request_id = request_id
    request.state.client_ip = client_ip
    if sentry_enabled():
        set_sentry_context(request_id=request_id)
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request completed",
        extra={
            "event": "http_request",
            "request_id": request_id,
            "ip_address": client_ip,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


# ── Startup ───────────────────────────────────────────────────────────
@app.on_event("startup")
def startup() -> None:
    setup_logging()
    init_sentry(environment="production" if not settings.DEBUG else "development")
    get_audit_logger()
    validate_security_config()
    ensure_alert_lifecycle_schema(engine)
    # Create all tables; Alembic migrations handle schema upgrades.
    Base.metadata.create_all(bind=engine)
    if settings.SEED_DATA:
        seed()
    else:
        logger.info("Database seeding skipped (SEED_DATA=false)")


@app.get("/")
def root():
    return {"message": "VisionSafe 360 API is running", "version": "1.0.0"}


# ── Route registration ────────────────────────────────────────────────
def _register_routes() -> None:
    # Versioned API — all new integrations should use /api/v1/
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(stats_router)
    # api_v1.include_router(health_router)
    api_v1.include_router(alerts_router)
    api_v1.include_router(cameras_router)
    api_v1.include_router(jobs_router)
    api_v1.include_router(media_router)
    api_v1.include_router(monitoring_router)
    api_v1.include_router(incidents_router)
    api_v1.include_router(users_router)
    api_v1.include_router(analytics_router)
    api_v1.include_router(auth_router)
    api_v1.include_router(ergonomics_router)
    api_v1.include_router(config_router)
    api_v1.include_router(notifications_router)
    api_v1.include_router(edge_config_router)
    api_v1.include_router(ingest_router)  # internal: edge AI → backend, no auth
    # api_v1.include_router(incidents_ws_router)
    # api_v1.include_router(notifications_ws_router)
    app.include_router(api_v1)

    # Backward-compatible /api prefix (current dashboard paths)
    legacy_api = APIRouter(prefix="/api")
    legacy_api.include_router(stats_router)
    legacy_api.include_router(alerts_router)
    legacy_api.include_router(cameras_router)
    legacy_api.include_router(jobs_router)
    legacy_api.include_router(media_router)
    legacy_api.include_router(monitoring_router)
    legacy_api.include_router(incidents_router)
    legacy_api.include_router(users_router)
    legacy_api.include_router(analytics_router)
    legacy_api.include_router(auth_router)
    legacy_api.include_router(ergonomics_router)
    legacy_api.include_router(config_router)
    legacy_api.include_router(notifications_router)
    legacy_api.include_router(edge_config_router)
    legacy_api.include_router(ingest_router)  # internal: edge AI → backend, no auth
    app.include_router(legacy_api)

    # Non-versioned health + WebSocket endpoints
    app.include_router(health_router)
    app.include_router(incidents_ws_router)
    app.include_router(notifications_ws_router)
    app.include_router(stream_ws_router)


_register_routes()
