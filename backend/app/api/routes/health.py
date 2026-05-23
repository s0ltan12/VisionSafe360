"""Health check endpoints for production deployment."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ...config.database import get_db
from ...services.redis_client import redis_available

router = APIRouter(tags=["health"])


@router.get("/healthz", status_code=200)
def liveness():
    """Liveness probe: returns 200 if the application process is running."""
    return {"status": "alive"}


@router.get("/readyz")
def readiness(db: Session = Depends(get_db)):
    """Readiness probe: verifies database and Redis connectivity.

    Returns 200 when all critical dependencies are reachable,
    503 otherwise so load balancers can stop routing traffic.

    Bug fixed: was `async def` using `await db.execute(select(1))`
    with a *synchronous* SQLAlchemy Session — crashes at runtime.
    Now correctly uses a synchronous session with `text()`.
    """
    checks: dict[str, str] = {}
    http_status = 200

    # ── Database check ────────────────────────────────────────────────
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        http_status = 503

    # ── Redis check ───────────────────────────────────────────────────
    try:
        if redis_available():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable (non-critical)"
            # Redis failing is non-critical: monitoring falls back in-process.
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    return JSONResponse(
        content={"ready": http_status == 200, **checks},
        status_code=http_status,
    )
