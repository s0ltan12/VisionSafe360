"""Analytics service — dashboard statistics and time-series aggregations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Alert, Camera, ErgonomicRecord, Incident, User


class AnalyticsService:
    @staticmethod
    def get_dashboard_stats(db: Session) -> dict:
        total_alerts = db.query(Alert).count()
        active_alerts = db.query(Alert).filter(Alert.status == "New").count()
        resolved_alerts = db.query(Alert).filter(Alert.status == "Resolved").count()
        total_cameras = db.query(Camera).count()
        online_cameras = db.query(Camera).filter(Camera.status == "Online").count()
        total_incidents = db.query(Incident).count()
        total_users = db.query(User).count()

        trends = AnalyticsService.get_incidents_time_series(db, days=7)

        return {
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "resolved_alerts": resolved_alerts,
            "total_cameras": total_cameras,
            "online_cameras": online_cameras,
            "offline_cameras": total_cameras - online_cameras,
            "total_incidents": total_incidents,
            "total_users": total_users,
            "trends": trends,
        }

    @staticmethod
    def get_incidents_time_series(
        db: Session,
        days: int = 30,
        severity: Optional[str] = None,
        zone: Optional[str] = None,
    ) -> list[dict]:
        """Return daily incident counts grouped by date for the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = db.query(
            func.date(Incident.created_at).label("date"),
            func.count(Incident.id).label("count"),
        ).filter(Incident.created_at >= cutoff)
        if severity:
            q = q.filter(Incident.severity == severity)
        if zone:
            q = q.filter(Incident.zone == zone)
        rows = q.group_by(func.date(Incident.created_at)).order_by("date").all()
        return [{"date": str(row.date), "count": row.count} for row in rows]

    @staticmethod
    def get_alerts_by_severity(db: Session) -> list[dict]:
        rows = db.query(
            Alert.severity.label("severity"),
            func.count(Alert.id).label("count"),
        ).group_by(Alert.severity).all()
        return [{"severity": row.severity, "count": row.count} for row in rows]

    @staticmethod
    def get_alerts_by_zone(db: Session, limit: int = 10) -> list[dict]:
        rows = db.query(
            Alert.zone.label("zone"),
            func.count(Alert.id).label("count"),
        ).group_by(Alert.zone).order_by(func.count(Alert.id).desc()).limit(limit).all()
        return [{"zone": row.zone, "count": row.count} for row in rows]

    @staticmethod
    def get_incidents_by_severity(db: Session) -> list[dict]:
        rows = db.query(
            Incident.severity.label("severity"),
            func.count(Incident.id).label("count"),
        ).group_by(Incident.severity).all()
        return [{"severity": row.severity, "count": row.count} for row in rows]

    @staticmethod
    def get_incidents_by_zone(db: Session, limit: int = 10) -> list[dict]:
        rows = db.query(
            Incident.zone.label("zone"),
            func.count(Incident.id).label("count"),
        ).group_by(Incident.zone).order_by(func.count(Incident.id).desc()).limit(limit).all()
        return [{"zone": row.zone, "count": row.count} for row in rows]

    @staticmethod
    def get_ergonomic_trend(db: Session, days: int = 7) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = db.query(
            func.date(ErgonomicRecord.recorded_at).label("date"),
            ErgonomicRecord.risk_level.label("risk_level"),
            func.count(ErgonomicRecord.id).label("count"),
        ).filter(ErgonomicRecord.recorded_at >= cutoff).group_by(
            func.date(ErgonomicRecord.recorded_at),
            ErgonomicRecord.risk_level,
        ).order_by("date").all()
        return [{"date": str(r.date), "risk_level": r.risk_level, "count": r.count} for r in rows]