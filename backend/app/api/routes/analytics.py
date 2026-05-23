"""Analytics routes — dashboard statistics and time-series data."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...services.analytics_service import AnalyticsService
from ...utils.permissions import require_roles

router = APIRouter(tags=["analytics"], dependencies=[Depends(require_roles("admin", "operator", "viewer"))])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Overall dashboard KPI summary."""
    return AnalyticsService.get_dashboard_stats(db)


@router.get("/incidents/time-series")
def incidents_time_series(
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    zone: Optional[str] = Query(None, description="Filter by zone"),
    db: Session = Depends(get_db),
):
    """Daily incident counts for the Reports page trend chart."""
    return AnalyticsService.get_incidents_time_series(db, days=days, severity=severity, zone=zone)


@router.get("/analytics/incidents/time-series")
def analytics_incidents_time_series(
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    zone: Optional[str] = Query(None, description="Filter by zone"),
    db: Session = Depends(get_db),
):
    return AnalyticsService.get_incidents_time_series(db, days=days, severity=severity, zone=zone)


@router.get("/alerts/by-severity")
def alerts_by_severity(db: Session = Depends(get_db)):
    return AnalyticsService.get_alerts_by_severity(db)


@router.get("/alerts/by-type")
def alerts_by_type(db: Session = Depends(get_db)):
    return AnalyticsService.get_alerts_by_type(db)


@router.get("/analytics/alerts/by-type")
def analytics_alerts_by_type(db: Session = Depends(get_db)):
    return AnalyticsService.get_alerts_by_type(db)


@router.get("/alerts/by-zone")
def alerts_by_zone(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return AnalyticsService.get_alerts_by_zone(db, limit=limit)


@router.get("/incidents/by-severity")
def incidents_by_severity(db: Session = Depends(get_db)):
    return AnalyticsService.get_incidents_by_severity(db)


@router.get("/incidents/by-zone")
def incidents_by_zone(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return AnalyticsService.get_incidents_by_zone(db, limit=limit)


@router.get("/ergonomics/trend")
def ergonomic_trend(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    return AnalyticsService.get_ergonomic_trend(db, days=days)
