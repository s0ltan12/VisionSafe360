"""Append-only incident timeline service."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..models import IncidentEvent, User


class IncidentTimelineService:
    @staticmethod
    def record_event(
        db: Session,
        *,
        incident_id: str,
        action: str,
        previous_status: str | None = None,
        new_status: str | None = None,
        actor: User | None = None,
        actor_name: str | None = None,
        note: str | None = None,
        metadata: dict | None = None,
    ) -> IncidentEvent:
        event = IncidentEvent(
            id=f"IE-{uuid.uuid4().hex[:12]}",
            incident_id=incident_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            actor_id=getattr(actor, "id", None),
            actor_name=getattr(actor, "name", None) or actor_name,
            note=note,
            event_metadata=metadata,
        )
        db.add(event)
        return event
