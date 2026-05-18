"""Analytics service — dashboard statistics and time-series aggregations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Alert, Camera, ErgonomicRecord, HazardTypeEnum, Incident, StatusEnum, User


class AnalyticsService:
    @staticmethod
    def get_dashboard_stats(db: Session) -> dict:
        total_alerts = db.query(Alert).count()
        active_alerts = db.query(Alert).filter(Alert.status.in_([StatusEnum.New, StatusEnum.Active])).count()
        resolved_alerts = db.query(Alert).filter(Alert.status == StatusEnum.Resolved).count()
        total_cameras = db.query(Camera).count()
        online_cameras = db.query(Camera).filter(Camera.status == "Online").count()
        total_incidents = db.query(Incident).count()
        total_users = db.query(User).count()
        falls_detected = db.query(Alert).filter(Alert.type == HazardTypeEnum.Fall).count()
        now = datetime.now(timezone.utc)
        current_window_start = now - timedelta(days=7)
        previous_window_start = now - timedelta(days=14)
        incidents_last_7_days = db.query(Incident).filter(Incident.created_at >= current_window_start).count()
        incidents_previous_7_days = db.query(Incident).filter(
            Incident.created_at >= previous_window_start,
            Incident.created_at < current_window_start,
        ).count()

        trends = AnalyticsService.get_incidents_time_series(db, days=7)
        safety_score = AnalyticsService._calculate_safety_score(
            active_alerts=active_alerts,
            total_incidents=total_incidents,
            online_cameras=online_cameras,
            total_cameras=total_cameras,
        )

        return {
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "resolved_alerts": resolved_alerts,
            "total_cameras": total_cameras,
            "online_cameras": online_cameras,
            "offline_cameras": total_cameras - online_cameras,
            "total_incidents": total_incidents,
            "total_users": total_users,
            "falls_detected": falls_detected,
            "safety_score": safety_score,
            "incidents_last_7_days": incidents_last_7_days,
            "incidents_previous_7_days": incidents_previous_7_days,
            "trends": trends,
        }

    @staticmethod
    def _calculate_safety_score(
        *,
        active_alerts: int,
        total_incidents: int,
        online_cameras: int,
        total_cameras: int,
    ) -> float:
        camera_health = (online_cameras / total_cameras) if total_cameras else 1.0
        alert_penalty = min(active_alerts * 3.0, 45.0)
        incident_penalty = min(total_incidents * 0.2, 35.0)
        score = (camera_health * 100.0) - alert_penalty - incident_penalty
        return round(max(0.0, min(100.0, score)), 1)

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
        return [{"severity": row.severity.value if hasattr(row.severity, "value") else str(row.severity), "count": row.count} for row in rows]

    @staticmethod
    def get_alerts_by_type(db: Session) -> list[dict]:
        rows = db.query(
            Alert.type.label("type"),
            func.count(Alert.id).label("count"),
        ).group_by(Alert.type).order_by(func.count(Alert.id).desc()).all()
        return [{"type": row.type.value if hasattr(row.type, "value") else str(row.type), "count": row.count} for row in rows]

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
        return [{"severity": row.severity.value if hasattr(row.severity, "value") else str(row.severity), "count": row.count} for row in rows]

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
        return [{
            "date": str(r.date),
            "risk_level": r.risk_level.value if hasattr(r.risk_level, "value") else str(r.risk_level),
            "count": r.count,
        } for r in rows]
