"""Incident SLA breach evaluation and analytics."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config.settings import settings
from ..models import Incident, IncidentStatusEnum, SeverityEnum
from .incident_command_service import IncidentCommandService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _severity_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


class SLAService:
    """Evaluate incident acknowledgement and resolution SLA thresholds."""

    ACK_THRESHOLDS = {
        "Critical": settings.SLA_ACK_CRITICAL_SECONDS,
        "High": settings.SLA_ACK_HIGH_SECONDS,
        "Medium": settings.SLA_ACK_MEDIUM_SECONDS,
        "Low": settings.SLA_ACK_LOW_SECONDS,
    }
    RESOLVE_THRESHOLDS = {
        "Critical": settings.SLA_RESOLVE_CRITICAL_SECONDS,
        "High": settings.SLA_RESOLVE_HIGH_SECONDS,
        "Medium": settings.SLA_RESOLVE_MEDIUM_SECONDS,
        "Low": settings.SLA_RESOLVE_LOW_SECONDS,
    }

    @classmethod
    def check_all(cls, db: Session, *, now: datetime | None = None) -> dict:
        now = now or _utcnow()
        incidents = (
            db.query(Incident)
            .filter(
                Incident.status.notin_(
                    [
                        IncidentStatusEnum.Resolved,
                        IncidentStatusEnum.False_Positive,
                        IncidentStatusEnum.Archived,
                    ]
                )
            )
            .all()
        )
        checked = 0
        breached = 0
        for incident in incidents:
            checked += 1
            breached += cls._check_one(db, incident, now=now)
        if breached:
            db.commit()
        return {"checked": checked, "breached": breached}

    @classmethod
    def check_incident(cls, db: Session, incident_id: str, *, now: datetime | None = None) -> Incident | None:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident is None:
            return None
        breached = cls._check_one(db, incident, now=now or _utcnow())
        if breached:
            db.commit()
            db.refresh(incident)
        return incident

    @classmethod
    def get_summary(cls, db: Session) -> dict:
        total = db.query(Incident).count()
        breached = db.query(Incident).filter(Incident.sla_breached_at.isnot(None)).count()
        acknowledged = db.query(Incident).filter(Incident.acknowledged_at.isnot(None)).all()
        response_seconds: list[float] = []
        for incident in acknowledged:
            start = incident.started_at or incident.created_at
            if start is not None and incident.acknowledged_at is not None:
                response_seconds.append(
                    max(0.0, (_aware(incident.acknowledged_at) - _aware(start)).total_seconds())
                )
        avg_response = round(sum(response_seconds) / len(response_seconds), 1) if response_seconds else 0.0
        return {
            "total_incidents": total,
            "sla_breach_count": breached,
            "sla_breach_rate": round((breached / total) if total else 0.0, 4),
            "avg_response_time_seconds": avg_response,
        }

    @classmethod
    def _check_one(cls, db: Session, incident: Incident, *, now: datetime) -> int:
        if incident.status in (
            IncidentStatusEnum.Resolved,
            IncidentStatusEnum.False_Positive,
            IncidentStatusEnum.Archived,
        ):
            return 0
        severity = _severity_value(incident.severity)
        start = _aware(incident.started_at or incident.created_at or now)
        elapsed = max(0.0, (_aware(now) - start).total_seconds())
        breached = 0

        ack_threshold = cls.ACK_THRESHOLDS.get(severity, settings.SLA_ACK_MEDIUM_SECONDS)
        if (
            incident.acknowledged_at is None
            and incident.sla_ack_breached_at is None
            and elapsed >= ack_threshold
        ):
            breached += cls._mark_breached(
                db,
                incident,
                now,
                breach_type="acknowledgement",
                threshold_seconds=ack_threshold,
                elapsed_seconds=elapsed,
            )

        resolve_threshold = cls.RESOLVE_THRESHOLDS.get(severity, settings.SLA_RESOLVE_MEDIUM_SECONDS)
        if (
            incident.resolved_at is None
            and incident.sla_resolution_breached_at is None
            and elapsed >= resolve_threshold
        ):
            breached += cls._mark_breached(
                db,
                incident,
                now,
                breach_type="resolution",
                threshold_seconds=resolve_threshold,
                elapsed_seconds=elapsed,
            )
        return breached

    @staticmethod
    def _mark_breached(
        db: Session,
        incident: Incident,
        now: datetime,
        *,
        breach_type: str,
        threshold_seconds: int,
        elapsed_seconds: float,
    ) -> int:
        IncidentCommandService.record_sla_breach(
            db,
            incident,
            breach_type=breach_type,
            threshold_seconds=threshold_seconds,
            elapsed_seconds=elapsed_seconds,
            now=now,
        )
        return 1
