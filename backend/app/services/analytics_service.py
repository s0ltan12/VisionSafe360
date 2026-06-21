"""Analytics service — dashboard statistics and time-series aggregations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models import Alert, Camera, ErgonomicRecord, HazardTypeEnum, Incident, IncidentStatusEnum, SeverityEnum, StatusEnum, User
from .sla_service import SLAService


class AnalyticsService:
    @staticmethod
    def get_dashboard_stats(db: Session) -> dict:
        total_alerts = db.query(Alert).count()
        active_alerts = db.query(Alert).filter(Alert.status.in_([StatusEnum.New, StatusEnum.Active])).count()
        resolved_alerts = db.query(Alert).filter(Alert.status == StatusEnum.Resolved).count()
        total_cameras = db.query(Camera).count()
        online_cameras = db.query(Camera).filter(Camera.status == "Online").count()
        total_incidents = db.query(Incident).count()
        active_incidents = db.query(Incident).filter(
            Incident.status.in_([IncidentStatusEnum.New, IncidentStatusEnum.Validating, IncidentStatusEnum.Active, IncidentStatusEnum.Acknowledged])
        ).count()
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
        avg_resolution_time = AnalyticsService.get_avg_resolution_time(db)
        top_dangerous_zones = AnalyticsService.get_top_dangerous_zones(db, limit=5)
        recurring_hazards = AnalyticsService.get_recurring_hazards(db, limit=5)
        weekly_summary = AnalyticsService.get_weekly_summary(db)
        sla_summary = SLAService.get_summary(db)
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
            "active_incidents": active_incidents,
            "total_users": total_users,
            "falls_detected": falls_detected,
            "safety_score": safety_score,
            "incidents_last_7_days": incidents_last_7_days,
            "incidents_previous_7_days": incidents_previous_7_days,
            "trends": trends,
            "avg_resolution_time_seconds": avg_resolution_time,
            "top_dangerous_zones": top_dangerous_zones,
            "recurring_hazards": recurring_hazards,
            "weekly_summary": weekly_summary,
            "sla_breach_count": sla_summary["sla_breach_count"],
            "sla_breach_rate": sla_summary["sla_breach_rate"],
            "avg_response_time_seconds": sla_summary["avg_response_time_seconds"],
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
        offline_penalty = (1.0 - camera_health) * 25.0
        alert_penalty = min(active_alerts * 2.0, 30.0)
        # Historical volume should not force the current safety score to zero.
        incident_penalty = min(total_incidents * 0.05, 15.0)
        score = 100.0 - offline_penalty - alert_penalty - incident_penalty
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
    def get_avg_resolution_time(db: Session) -> float:
        avg_seconds = (
            db.query(func.avg(Incident.duration_seconds))
            .filter(Incident.duration_seconds.isnot(None))
            .scalar()
        )
        return round(float(avg_seconds or 0.0), 1)

    @staticmethod
    def get_recurring_hazards(db: Session, limit: int = 10) -> list[dict]:
        rows = (
            db.query(
                Incident.zone.label("zone"),
                Incident.classification.label("classification"),
                func.count(Incident.id).label("count"),
            )
            .group_by(Incident.zone, Incident.classification)
            .having(func.count(Incident.id) > 1)
            .order_by(func.count(Incident.id).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "zone": row.zone,
                "classification": row.classification,
                "count": row.count,
            }
            for row in rows
        ]

    @staticmethod
    def get_top_dangerous_zones(db: Session, limit: int = 10) -> list[dict]:
        severity_weight = case(
            (Incident.severity == SeverityEnum.Critical, 4),
            (Incident.severity == SeverityEnum.High, 3),
            (Incident.severity == SeverityEnum.Medium, 2),
            else_=1,
        )
        risk_score = func.sum(severity_weight)
        rows = (
            db.query(
                Incident.zone.label("zone"),
                func.count(Incident.id).label("incident_count"),
                risk_score.label("risk_score"),
            )
            .group_by(Incident.zone)
            .order_by(risk_score.desc(), func.count(Incident.id).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "zone": row.zone,
                "incident_count": int(row.incident_count or 0),
                "risk_score": int(row.risk_score or 0),
            }
            for row in rows
        ]

    @staticmethod
    def get_weekly_summary(db: Session) -> dict:
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        previous_start = now - timedelta(days=14)
        current = db.query(Incident).filter(Incident.created_at >= week_start).count()
        previous = db.query(Incident).filter(
            Incident.created_at >= previous_start,
            Incident.created_at < week_start,
        ).count()
        resolved = db.query(Incident).filter(Incident.resolved_at >= week_start).count()
        return {
            "incidents": current,
            "previous_incidents": previous,
            "resolved": resolved,
            "delta": current - previous,
        }

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
