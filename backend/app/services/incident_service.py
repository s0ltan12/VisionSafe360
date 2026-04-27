"""Incident business logic with pagination support."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Incident
from ..schemas import IncidentCreate, IncidentUpdate


class IncidentService:
    @staticmethod
    def list(db: Session, skip: int = 0, limit: int = 50) -> tuple[list[Incident], int]:
        total = db.query(Incident).count()
        items = db.query(Incident).order_by(Incident.created_at.desc()).offset(skip).limit(limit).all()
        return items, total

    @staticmethod
    def get(db: Session, incident_id: str) -> Incident | None:
        return db.query(Incident).filter(Incident.id == incident_id).first()

    @staticmethod
    def create(db: Session, payload: IncidentCreate) -> Incident:
        incident = Incident(**payload.model_dump())
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return incident

    @staticmethod
    def update(db: Session, incident_id: str, payload: IncidentUpdate) -> Incident | None:
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