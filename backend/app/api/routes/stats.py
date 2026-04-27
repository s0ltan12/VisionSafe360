"""Shortcut /stats route — maps the legacy frontend call to analytics service."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...services.analytics_service import AnalyticsService
from ...utils.security import get_current_user

router = APIRouter(tags=["stats"], dependencies=[Depends(get_current_user)])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Dashboard KPI summary — called directly by the frontend StatsAPI."""
    return AnalyticsService.get_dashboard_stats(db)
