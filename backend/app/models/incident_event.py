"""Incident lifecycle timeline event ORM model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, JSON, String, Text

from ..config.database import Base
from .timestamps import utcnow


class IncidentEvent(Base):
    """Append-only incident lifecycle timeline entry."""

    __tablename__ = "incident_events"
    __table_args__ = (
        Index("ix_incident_events_incident_id", "incident_id"),
        Index("ix_incident_events_created_at", "created_at"),
    )

    id = Column(String, primary_key=True, index=True)
    incident_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    actor_id = Column(String, nullable=True)
    actor_name = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
