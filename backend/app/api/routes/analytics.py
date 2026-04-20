"""Analytics routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...services.analytics_service import AnalyticsService
from ...utils.security import get_current_user

router = APIRouter(tags=["analytics"], dependencies=[Depends(get_current_user)])


@router.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
	return AnalyticsService.get_dashboard_stats(db)