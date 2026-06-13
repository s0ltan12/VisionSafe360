"""Authoritative incident lifecycle command service."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Alert, Incident, IncidentStatusEnum, SeverityEnum, StatusEnum, User
from .alert_service import AlertService
from .incident_timeline_service import IncidentTimelineService
from .notification_dispatch_service import NotificationDispatchService


ACTIVE_STATUSES = {
    IncidentStatusEnum.New,
    IncidentStatusEnum.Validating,
    IncidentStatusEnum.Active,
    IncidentStatusEnum.Acknowledged,
}
HISTORY_STATUSES = {
    IncidentStatusEnum.Resolved,
    IncidentStatusEnum.False_Positive,
    IncidentStatusEnum.Archived,
}


ALLOWED_INCIDENT_TRANSITIONS: dict[str, set[str]] = {
    "New": {"Validating", "Active", "Acknowledged", "Resolved", "False Positive", "Archived"},
    "Validating": {"Active", "Resolved", "False Positive", "Archived"},
    "Active": {"Acknowledged", "Resolved", "False Positive", "Archived"},
    "Acknowledged": {"Resolved", "False Positive", "Archived"},
    "Resolved": {"Archived", "Active"},
    "False Positive": {"Archived", "Active"},
    "Archived": {"Active"},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _severity_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


class IncidentCommandService:
    """Single mutation boundary for incident lifecycle and audit timeline."""

    @staticmethod
    def get(db: Session, incident_id: str) -> Incident | None:
        return db.query(Incident).filter(Incident.id == incident_id).first()

    @staticmethod
    def transition_status(
        db: Session,
        incident_id: str,
        status: IncidentStatusEnum | str,
        *,
        actor: User | None = None,
        actor_name: str | None = None,
        note: str | None = None,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> Incident | None:
        incident = IncidentCommandService.get(db, incident_id)
        if incident is None:
            return None
        return IncidentCommandService.transition_status_for_incident(
            db,
            incident,
            status,
            actor=actor,
            actor_name=actor_name,
            note=note,
            metadata=metadata,
            commit=commit,
        )

    @staticmethod
    def transition_status_for_incident(
        db: Session,
        incident: Incident,
        status: IncidentStatusEnum | str,
        *,
        actor: User | None = None,
        actor_name: str | None = None,
        note: str | None = None,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> Incident:
        previous = _status_value(incident.status)
        new = _status_value(status)
        if previous == new:
            return incident

        allowed = ALLOWED_INCIDENT_TRANSITIONS.get(previous, set())
        if new not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid incident status transition: {previous} -> {new}",
            )

        now = _utcnow()
        incident.status = IncidentStatusEnum(new)
        IncidentCommandService._apply_status_fields(incident, new, now, actor)
        IncidentTimelineService.record_event(
            db,
            incident_id=incident.id,
            action=IncidentCommandService._action_for_status(new, previous),
            previous_status=previous,
            new_status=new,
            actor=actor,
            actor_name=actor_name,
            note=note,
            metadata=metadata,
        )
        IncidentCommandService._sync_linked_alerts(
            db,
            incident,
            previous_status=previous,
            action=IncidentCommandService._action_for_status(new, previous),
            actor=actor,
            actor_name=actor_name,
            note=note,
        )
        IncidentCommandService._record_notification(db, incident, new, previous)
        if commit:
            db.commit()
            db.refresh(incident)
        return incident

    @staticmethod
    def acknowledge(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        return IncidentCommandService.transition_status(
            db,
            incident_id,
            IncidentStatusEnum.Acknowledged,
            actor=actor,
            note=note,
        )

    @staticmethod
    def resolve(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        return IncidentCommandService.transition_status(
            db,
            incident_id,
            IncidentStatusEnum.Resolved,
            actor=actor,
            note=note,
        )

    @staticmethod
    def archive(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        return IncidentCommandService.transition_status(
            db,
            incident_id,
            IncidentStatusEnum.Archived,
            actor=actor,
            note=note,
        )

    @staticmethod
    def reopen(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        return IncidentCommandService.transition_status(
            db,
            incident_id,
            IncidentStatusEnum.Active,
            actor=actor,
            note=note or "Incident reopened",
        )

    @staticmethod
    def false_positive(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        return IncidentCommandService.transition_status(
            db,
            incident_id,
            IncidentStatusEnum.False_Positive,
            actor=actor,
            note=note,
        )

    @staticmethod
    def escalate(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
        target_severity: SeverityEnum | str | None = None,
    ) -> Incident | None:
        incident = IncidentCommandService.get(db, incident_id)
        if incident is None:
            return None
        previous_severity = _severity_value(incident.severity)
        new_severity = IncidentCommandService._next_severity(incident.severity, target_severity)
        incident.severity = new_severity
        incident.escalation_count = int(incident.escalation_count or 0) + 1
        IncidentTimelineService.record_event(
            db,
            incident_id=incident.id,
            action="escalated",
            previous_status=_status_value(incident.status),
            new_status=_status_value(incident.status),
            actor=actor,
            note=note,
            metadata={
                "previous_severity": previous_severity,
                "new_severity": _severity_value(new_severity),
                "escalation_count": incident.escalation_count,
            },
        )
        NotificationDispatchService.record_incident_notification(
            db,
            incident=incident,
            action="incident_escalated",
            message=f"{incident.id} escalated to {_severity_value(new_severity)}",
        )
        IncidentCommandService._sync_linked_alerts(
            db,
            incident,
            previous_status=_status_value(incident.status),
            action="escalated",
            actor=actor,
            note=note,
            previous_severity=previous_severity,
        )
        db.commit()
        db.refresh(incident)
        return incident

    @staticmethod
    def record_sla_breach(
        db: Session,
        incident: Incident,
        *,
        breach_type: str,
        threshold_seconds: int,
        elapsed_seconds: float,
        now: datetime | None = None,
    ) -> None:
        now = now or _utcnow()
        if incident.sla_breached_at is None:
            incident.sla_breached_at = now
        if breach_type == "acknowledgement" and incident.sla_ack_breached_at is None:
            incident.sla_ack_breached_at = now
        if breach_type == "resolution" and incident.sla_resolution_breached_at is None:
            incident.sla_resolution_breached_at = now
        incident.sla_breach_count = int(incident.sla_breach_count or 0) + 1
        IncidentTimelineService.record_event(
            db,
            incident_id=incident.id,
            action="sla_breached",
            previous_status=_status_value(incident.status),
            new_status=_status_value(incident.status),
            actor_name="SLA Engine",
            note=f"{breach_type.title()} SLA breached",
            metadata={
                "breach_type": breach_type,
                "severity": _severity_value(incident.severity),
                "threshold_seconds": threshold_seconds,
                "elapsed_seconds": round(elapsed_seconds, 1),
            },
        )
        NotificationDispatchService.record_incident_notification(
            db,
            incident=incident,
            action="sla_breached",
            message=f"{incident.id}: {breach_type} SLA breached",
        )

    @staticmethod
    def _apply_status_fields(incident: Incident, status: str, now: datetime, actor: User | None) -> None:
        actor_name = getattr(actor, "name", None)
        if status == "Validating":
            if incident.started_at is None:
                incident.started_at = now
        elif status == "Active":
            if incident.started_at is None:
                incident.started_at = now
            if incident.validated_at is None:
                incident.validated_at = now
        elif status == "Acknowledged":
            incident.acknowledged_at = now
            incident.acknowledged_by = actor_name
        elif status in {"Resolved", "False Positive"}:
            incident.resolved_at = now
            incident.resolved_by = actor_name
            start = incident.started_at or incident.validated_at or incident.created_at
            if start is not None:
                incident.duration_seconds = max(0, int((_ensure_aware(now) - _ensure_aware(start)).total_seconds()))
        elif status == "Archived":
            incident.archived_at = now

    @staticmethod
    def _action_for_status(status: str, previous: str) -> str:
        if previous in {"Resolved", "False Positive", "Archived"} and status == "Active":
            return "reopened"
        return {
            "Validating": "validating",
            "Active": "active",
            "Acknowledged": "acknowledged",
            "Resolved": "resolved",
            "False Positive": "false_positive",
            "Archived": "archived",
        }.get(status, "status_changed")

    @staticmethod
    def _record_notification(db: Session, incident: Incident, status: str, previous: str) -> None:
        action = {
            "Acknowledged": "incident_acknowledged",
            "Resolved": "incident_resolved",
            "Archived": "incident_archived",
        }.get(status)
        if status == "Active" and previous in {"Resolved", "False Positive", "Archived"}:
            action = "incident_reopened"
        if action:
            NotificationDispatchService.record_incident_notification(db, incident=incident, action=action)

    @staticmethod
    def _alert_status_for_incident(status: str) -> StatusEnum:
        return {
            "New": StatusEnum.New,
            "Validating": StatusEnum.Active,
            "Active": StatusEnum.Active,
            "Acknowledged": StatusEnum.Acknowledged,
            "Resolved": StatusEnum.Resolved,
            "False Positive": StatusEnum.False_Positive,
            "Archived": StatusEnum.Archived,
        }.get(status, StatusEnum.Active)

    @staticmethod
    def _sync_linked_alerts(
        db: Session,
        incident: Incident,
        *,
        previous_status: str,
        action: str,
        actor: User | None = None,
        actor_name: str | None = None,
        note: str | None = None,
        previous_severity: str | None = None,
    ) -> None:
        """Mirror incident-owned state onto linked alert signals for dashboard consistency."""
        alerts = db.query(Alert).filter(Alert.incident_id == incident.id).all()
        if not alerts:
            return

        incident_status = _status_value(incident.status)
        alert_status = IncidentCommandService._alert_status_for_incident(incident_status)
        now = _utcnow()

        for alert in alerts:
            old_alert_status = _status_value(alert.status)
            old_alert_severity = _severity_value(alert.severity)
            changed = False

            if alert.status != alert_status:
                alert.status = alert_status
                changed = True
            if alert.severity != incident.severity:
                alert.severity = incident.severity
                changed = True

            if incident_status == "Acknowledged":
                alert.acknowledged_at = incident.acknowledged_at or now
                alert.acknowledged_by = incident.acknowledged_by
                alert.acknowledged_by_id = getattr(actor, "id", None)
            elif incident_status == "Resolved":
                alert.resolved_at = incident.resolved_at or now
                alert.resolved_by = incident.resolved_by
                alert.resolved_by_id = getattr(actor, "id", None)
            elif incident_status == "False Positive":
                alert.false_positive_at = incident.resolved_at or now
                alert.false_positive_by = incident.resolved_by
                alert.false_positive_by_id = getattr(actor, "id", None)
            elif incident_status == "Archived":
                alert.archived_at = incident.archived_at or now
                alert.archived_by = getattr(actor, "name", None) or actor_name
                alert.archived_by_id = getattr(actor, "id", None)
            elif incident_status in {"Active", "New", "Validating"} and previous_status in {"Resolved", "False Positive", "Archived"}:
                alert.resolved_at = None
                alert.resolved_by = None
                alert.resolved_by_id = None
                alert.archived_at = None
                alert.archived_by = None
                alert.archived_by_id = None
                alert.false_positive_at = None
                alert.false_positive_by = None
                alert.false_positive_by_id = None

            if changed or action == "escalated":
                AlertService.record_event(
                    db,
                    alert_id=alert.id,
                    action=f"incident_{action}",
                    previous_status=old_alert_status,
                    new_status=_status_value(alert.status),
                    actor=actor,
                    actor_name=actor_name,
                    note=note or f"Linked incident {incident.id} {action.replace('_', ' ')}",
                    metadata={
                        "incident_id": incident.id,
                        "incident_status": incident_status,
                        "incident_previous_status": previous_status,
                        "previous_severity": previous_severity or old_alert_severity,
                        "new_severity": _severity_value(alert.severity),
                    },
                )

    @staticmethod
    def _next_severity(current: SeverityEnum, target: SeverityEnum | str | None) -> SeverityEnum:
        if target is not None:
            if isinstance(target, SeverityEnum):
                return target
            mapped = {
                "CRITICAL": SeverityEnum.Critical,
                "HIGH": SeverityEnum.High,
                "MEDIUM": SeverityEnum.Medium,
                "LOW": SeverityEnum.Low,
            }.get(str(target).strip().upper())
            return mapped or SeverityEnum(str(target))
        order = [SeverityEnum.Low, SeverityEnum.Medium, SeverityEnum.High, SeverityEnum.Critical]
        try:
            idx = order.index(current)
        except ValueError:
            return SeverityEnum.High
        return order[min(idx + 1, len(order) - 1)]
