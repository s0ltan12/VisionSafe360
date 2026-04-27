"""Alert business logic with pagination support."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Alert
from ..schemas import AlertCreate, AlertUpdate


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
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def update(db: Session, alert_id: str, payload: AlertUpdate) -> Alert | None:
        alert = AlertService.get(db, alert_id)
        if not alert:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(alert, field, value)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def delete(db: Session, alert_id: str) -> bool:
        alert = AlertService.get(db, alert_id)
        if not alert:
            return False
        db.delete(alert)
        db.commit()
        return True