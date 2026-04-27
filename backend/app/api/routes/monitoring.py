"""Runtime monitoring routes for lightweight production operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services.monitoring_service import monitoring_service
from ...services.rate_limit_service import rate_limit_service
from ...utils.permissions import require_roles

router = APIRouter(prefix="/monitoring", tags=["monitoring"], dependencies=[Depends(require_roles("admin"))])


@router.get("/metrics")
def get_metrics() -> dict:
	return {
		"rate_limit": rate_limit_service.snapshot(),
		"runtime": monitoring_service.snapshot(),
	}
