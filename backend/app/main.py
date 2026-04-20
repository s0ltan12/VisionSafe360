"""FastAPI app for VisionSafe backend."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.alerts import router as alerts_router
from .api.routes.analytics import router as analytics_router
from .api.routes.auth import router as auth_router
from .api.routes.cameras import router as cameras_router
from .api.routes.jobs import router as jobs_router
from .api.routes.media import router as media_router
from .api.routes.monitoring import router as monitoring_router
from .api.routes.incidents import router as incidents_router
from .api.routes.users import router as users_router
from .api.websocket.ws_handler import router as incidents_ws_router
from .seed import seed
from .utils.logging_config import setup_logging
from .utils.security import validate_security_config

app = FastAPI(
	title="VisionSafe 360 API",
	version="1.0.0",
	description="Backend API for VisionSafe 360 Safety Dashboard",
)

logger = logging.getLogger("visionsafe.backend")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
	allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
	request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
	start = time.perf_counter()
	response = await call_next(request)
	duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
	response.headers["x-request-id"] = request_id
	logger.info(
		"request completed",
		extra={
			"event": "http_request",
			"request_id": request_id,
			"method": request.method,
			"path": request.url.path,
			"status_code": response.status_code,
			"duration_ms": duration_ms,
		},
	)
	return response


@app.on_event("startup")
def startup() -> None:
	setup_logging()
	validate_security_config()
	seed()


@app.get("/")
def root():
	return {"message": "VisionSafe 360 API is running", "version": "1.0.0"}

app.include_router(alerts_router)
app.include_router(cameras_router)
app.include_router(jobs_router)
app.include_router(media_router)
app.include_router(monitoring_router)
app.include_router(incidents_router)
app.include_router(users_router)
app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(incidents_ws_router)
