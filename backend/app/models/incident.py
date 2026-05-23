"""Incident ORM model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Enum as PgEnum, Index, String, Text

from ..config.database import Base
from .enums import SeverityEnum
from .timestamps import utcnow


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_zone", "zone"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_camera_id", "camera_id"),
        Index("ix_incidents_worker_id", "worker_id"),
        Index("ix_incidents_created_at", "created_at"),
    )

    id                = Column(String, primary_key=True, index=True)
    zone              = Column(String, nullable=False)
    classification    = Column(String, nullable=False)
    severity          = Column(PgEnum(SeverityEnum, name="severity", create_type=False), nullable=False)
    camera_id         = Column(String, nullable=True)
    camera_name       = Column(String, nullable=True)
    worker_id         = Column(String, nullable=True)
    worker_gpu_id     = Column(String, nullable=True)
    root_cause        = Column(Text, default="Under Investigation")
    corrective_action = Column(Text, default="Pending Review")
    created_at        = Column(DateTime(timezone=True), nullable=False, default=utcnow)
