"""Runtime monitoring routes for lightweight production operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services.monitoring_service import monitoring_service
from ...services.rate_limit_service import rate_limit_service
from ...services.system_health_service import system_health_service
from ...config.database import get_db
from ...utils.permissions import require_roles
from sqlalchemy.orm import Session

router = APIRouter(prefix="/monitoring", tags=["monitoring"], dependencies=[Depends(require_roles("admin"))])


@router.get("/metrics")
def get_metrics() -> dict:
	return {
		"rate_limit": rate_limit_service.snapshot(),
		"runtime": monitoring_service.snapshot(),
	}


@router.get("/system-health")
def get_system_health(db: Session = Depends(get_db)) -> dict:
	return system_health_service.get_summary(db)
