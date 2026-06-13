"""Incident business logic with pagination support."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.orm import Session

from ..models import Incident, IncidentEvent, IncidentStatusEnum, SeverityEnum, User
from ..schemas import IncidentCreate, IncidentUpdate
from .incident_command_service import ACTIVE_STATUSES, HISTORY_STATUSES, IncidentCommandService
from .incident_timeline_service import IncidentTimelineService
from .notification_dispatch_service import NotificationDispatchService


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IncidentService:
    @staticmethod
    def list(db: Session, skip: int = 0, limit: int = 50, view: str | None = None) -> tuple[list[Incident], int]:
        query = db.query(Incident)
        if view == "active":
            query = query.filter(Incident.status.in_(list(ACTIVE_STATUSES)))
        elif view == "history":
            query = query.filter(Incident.status.in_(list(HISTORY_STATUSES)))
        total = query.count()
        severity_rank = case(
            (Incident.severity == SeverityEnum.Critical, 0),
            (Incident.severity == SeverityEnum.High, 1),
            (Incident.severity == SeverityEnum.Medium, 2),
            else_=3,
        )
        items = (
            query
            .order_by(severity_rank.asc(), Incident.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def get(db: Session, incident_id: str) -> Incident | None:
        return db.query(Incident).filter(Incident.id == incident_id).first()

    @staticmethod
    def create(db: Session, payload: IncidentCreate) -> Incident:
        incident = Incident(**payload.model_dump())
        if incident.started_at is None:
            incident.started_at = incident.created_at or _utcnow()
        db.add(incident)
        db.flush()
        IncidentTimelineService.record_event(
            db,
            incident_id=incident.id,
            action="created",
            previous_status=None,
            new_status=_status_value(incident.status),
            actor_name="System",
            note="Incident created",
        )
        NotificationDispatchService.record_incident_notification(
            db,
            incident=incident,
            action="incident_created",
        )
        db.commit()
        db.refresh(incident)
        return incident

    @staticmethod
    def update(db: Session, incident_id: str, payload: IncidentUpdate) -> Incident | None:
        incident = IncidentService.get(db, incident_id)
        if not incident:
            return None
        changes = payload.model_dump(exclude_unset=True)
        if "status" in changes or "severity" in changes:
            raise HTTPException(
                status_code=400,
                detail="Use incident command endpoints for lifecycle or severity changes",
            )
        for field, value in changes.items():
            setattr(incident, field, value)
        db.commit()
        db.refresh(incident)
        return incident

    @staticmethod
    def list_events(db: Session, incident_id: str) -> list[IncidentEvent]:
        return (
            db.query(IncidentEvent)
            .filter(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at.asc())
            .all()
        )

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
    ) -> Incident | None:
        return IncidentCommandService.transition_status(
            db,
            incident_id,
            status,
            actor=actor,
            actor_name=actor_name,
            note=note,
            metadata=metadata,
        )

    @staticmethod
    def acknowledge(
        db: Session,
        incident_id: str,
        *,
        actor: User | None = None,
        note: str | None = None,
    ) -> Incident | None:
        return IncidentService.transition_status(
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
        return IncidentService.transition_status(
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
        return IncidentService.transition_status(
            db,
            incident_id,
            IncidentStatusEnum.Archived,
            actor=actor,
            note=note,
        )

    @staticmethod
    def auto_resolve_check(db: Session, active_incident_ids: set[str]) -> int:
        stale = (
            db.query(Incident)
            .filter(Incident.status.in_([IncidentStatusEnum.Active, IncidentStatusEnum.Acknowledged]))
            .filter(~Incident.id.in_(active_incident_ids) if active_incident_ids else True)
            .all()
        )
        for incident in stale:
            IncidentCommandService.transition_status_for_incident(
                db,
                incident,
                IncidentStatusEnum.Resolved,
                actor_name="System",
                note="Incident auto-resolved because the hazard cleared",
                commit=False,
            )
        if stale:
            db.commit()
        return len(stale)

    @staticmethod
    def delete(db: Session, incident_id: str) -> bool:
        incident = IncidentService.get(db, incident_id)
        if not incident:
            return False
        db.delete(incident)
        db.commit()
        return True
