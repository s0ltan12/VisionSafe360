"""Incident business logic."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Incident
from ..schemas import IncidentCreate, IncidentUpdate


class IncidentService:
	@staticmethod
	def list(db: Session):
		return db.query(Incident).all()

	@staticmethod
	def get(db: Session, incident_id: str):
		return db.query(Incident).filter(Incident.id == incident_id).first()

	@staticmethod
	def create(db: Session, payload: IncidentCreate):
		incident = Incident(**payload.model_dump())
		db.add(incident)
		db.commit()
		db.refresh(incident)
		return incident

	@staticmethod
	def update(db: Session, incident_id: str, payload: IncidentUpdate):
		incident = IncidentService.get(db, incident_id)
		if not incident:
			return None
		for field, value in payload.model_dump(exclude_unset=True).items():
			setattr(incident, field, value)
		db.commit()
		db.refresh(incident)
		return incident

	@staticmethod
	def delete(db: Session, incident_id: str) -> bool:
		incident = IncidentService.get(db, incident_id)
		if not incident:
			return False
		db.delete(incident)
		db.commit()
		return True