"""Runtime monitoring routes for lightweight production operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services.monitoring_service import monitoring_service
from ...services.rate_limit_service import rate_limit_service
from ...utils.security import get_current_user

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"], dependencies=[Depends(get_current_user)])


@router.get("/metrics")
def get_metrics() -> dict:
	return {
		"rate_limit": rate_limit_service.snapshot(),
		"runtime": monitoring_service.snapshot(),
	}
