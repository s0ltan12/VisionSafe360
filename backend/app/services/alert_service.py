"""Alert business logic."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Alert
from ..schemas import AlertCreate, AlertUpdate


class AlertService:
	@staticmethod
	def list(db: Session):
		return db.query(Alert).all()

	@staticmethod
	def get(db: Session, alert_id: str):
		return db.query(Alert).filter(Alert.id == alert_id).first()

	@staticmethod
	def create(db: Session, payload: AlertCreate):
		alert = Alert(**payload.model_dump())
		db.add(alert)
		db.commit()
		db.refresh(alert)
		return alert

	@staticmethod
	def update(db: Session, alert_id: str, payload: AlertUpdate):
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