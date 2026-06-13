"""Persisted notification generation for incident operations."""
from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Incident, Notification


class NotificationDispatchService:
    """Create durable dashboard notifications from incident lifecycle events."""

    ACTION_TITLES = {
        "incident_created": "Incident created",
        "incident_escalated": "Incident escalated",
        "incident_acknowledged": "Incident acknowledged",
        "incident_resolved": "Incident resolved",
        "incident_reopened": "Incident reopened",
        "incident_archived": "Incident archived",
        "sla_breached": "SLA breached",
    }

    @staticmethod
    def record_incident_notification(
        db: Session,
        *,
        incident: Incident,
        action: str,
        message: str | None = None,
        idempotency_key: str | None = None,
    ) -> Notification:
        notification_id = (
            f"NOTIF-{hashlib.sha1(idempotency_key.encode('utf-8')).hexdigest()[:12]}"
            if idempotency_key
            else f"NOTIF-{uuid.uuid4().hex[:12]}"
        )
        if idempotency_key:
            existing = db.query(Notification).filter(Notification.id == notification_id).first()
            if existing is not None:
                return existing
        title = NotificationDispatchService.ACTION_TITLES.get(action, "Incident update")
        severity = incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity)
        row = Notification(
            id=notification_id,
            user_id=None,
            title=title,
            message=message or f"{incident.id}: {incident.classification} ({severity})",
            type="alert" if action in {"incident_created", "incident_escalated", "sla_breached"} else "info",
            source="incident_command",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        return row
