"""Alert business logic with pagination support."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Alert, AlertEvent, User
from ..schemas import AlertCreate, AlertUpdate


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "New": {"Acknowledged", "In Investigation", "Resolved", "False Positive", "Archived"},
    "Acknowledged": {"In Investigation", "Resolved", "False Positive", "Archived"},
    "In Investigation": {"Resolved", "False Positive", "Archived"},
    "Resolved": {"Archived"},
    "False Positive": {"Archived"},
    "Archived": set(),
    "Dismissed": set(),
    "Notified": {"Acknowledged", "In Investigation", "Resolved", "False Positive", "Archived"},
    "Active": {"Acknowledged", "In Investigation", "Resolved", "False Positive", "Archived"},
}


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertService:
    @staticmethod
    def list(db: Session, skip: int = 0, limit: int = 50) -> tuple[list[Alert], int]:
        total = db.query(Alert).count()
        items = db.query(Alert).order_by(Alert.created_at.desc()).offset(skip).limit(limit).all()
        return items, total

    @staticmethod
    def get(db: Session, alert_id: str) -> Alert | None:
        return db.query(Alert).filter(Alert.id == alert_id).first()

    @staticmethod
    def create(db: Session, payload: AlertCreate) -> Alert:
        alert = Alert(**payload.model_dump())
        db.add(alert)
        db.flush()
        AlertService.record_event(
            db,
            alert_id=alert.id,
            action="created",
            previous_status=None,
            new_status=_status_value(alert.status),
            actor_name="Edge AI",
            note="Alert created",
        )
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def update(
        db: Session,
        alert_id: str,
        payload: AlertUpdate,
        *,
        actor: User | None = None,
    ) -> Alert | None:
        alert = AlertService.get(db, alert_id)
        if not alert:
            return None
        changes = payload.model_dump(exclude_unset=True)
        note = changes.pop("note", None)

        previous_status = _status_value(alert.status)
        new_status = changes.get("status")
        if new_status is not None and new_status != previous_status:
            AlertService._validate_transition(previous_status, str(new_status))
            AlertService._apply_status_attribution(alert, str(new_status), actor)

        for field, value in changes.items():
            setattr(alert, field, value)

        if new_status is not None and str(new_status) != previous_status:
            AlertService.record_event(
                db,
                alert_id=alert.id,
                action=AlertService._action_for_status(str(new_status)),
                previous_status=previous_status,
                new_status=str(new_status),
                actor=actor,
                note=note,
            )
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def list_events(db: Session, alert_id: str) -> list[AlertEvent]:
        return (
            db.query(AlertEvent)
            .filter(AlertEvent.alert_id == alert_id)
            .order_by(AlertEvent.created_at.asc())
            .all()
        )

    @staticmethod
    def record_event(
        db: Session,
        *,
        alert_id: str,
        action: str,
        previous_status: str | None = None,
        new_status: str | None = None,
        actor: User | None = None,
        actor_name: str | None = None,
        note: str | None = None,
        metadata: dict | None = None,
    ) -> AlertEvent:
        event = AlertEvent(
            id=f"AE-{uuid.uuid4().hex[:12]}",
            alert_id=alert_id,
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

    @staticmethod
    def _validate_transition(previous: str, new: str) -> None:
        allowed = ALLOWED_TRANSITIONS.get(previous, set())
        if new not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid alert status transition: {previous} -> {new}",
            )

    @staticmethod
    def _apply_status_attribution(alert: Alert, status: str, actor: User | None) -> None:
        now = _utcnow()
        actor_name = getattr(actor, "name", None)
        actor_id = getattr(actor, "id", None)
        if status == "Acknowledged":
            alert.acknowledged_at = now
            alert.acknowledged_by = actor_name
            alert.acknowledged_by_id = actor_id
        elif status == "Resolved":
            alert.resolved_at = now
            alert.resolved_by = actor_name
            alert.resolved_by_id = actor_id
        elif status == "Archived":
            alert.archived_at = now
            alert.archived_by = actor_name
            alert.archived_by_id = actor_id
        elif status == "False Positive":
            alert.false_positive_at = now
            alert.false_positive_by = actor_name
            alert.false_positive_by_id = actor_id

    @staticmethod
    def _action_for_status(status: str) -> str:
        return {
            "Acknowledged": "acknowledged",
            "In Investigation": "investigating",
            "Resolved": "resolved",
            "False Positive": "false_positive",
            "Archived": "archived",
        }.get(status, "status_changed")

    @staticmethod
    def delete(db: Session, alert_id: str) -> bool:
        alert = AlertService.get(db, alert_id)
        if not alert:
            return False
        db.delete(alert)
        db.commit()
        return True
