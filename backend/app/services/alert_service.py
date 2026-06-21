"""Alert business logic with pagination support."""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Alert, AlertEvent, User
from ..schemas import AlertCreate, AlertUpdate
from .realtime_event_service import publish_alert_change, publish_alert_deleted


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


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
        data = payload.model_dump()
        if data.get("incident_id") and str(data.get("status", "New")) != "New":
            raise HTTPException(
                status_code=409,
                detail="Linked alerts must start as New; incident lifecycle owns operations",
            )
        alert = Alert(**data)
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
        publish_alert_change(alert, "alert_created")
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
        if (new_status is not None and new_status != previous_status) or "severity" in changes:
            raise HTTPException(
                status_code=409,
                detail="Alerts are detection signals; use incident command endpoints for lifecycle or severity state",
            )

        for field, value in changes.items():
            setattr(alert, field, value)

        db.commit()
        db.refresh(alert)
        publish_alert_change(alert, "alert_updated")
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
    def delete(db: Session, alert_id: str) -> bool:
        alert = AlertService.get(db, alert_id)
        if not alert:
            return False
        db.delete(alert)
        db.commit()
        publish_alert_deleted(alert_id)
        return True
