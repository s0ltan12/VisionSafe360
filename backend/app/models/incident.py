"""Incident ORM model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Enum as PgEnum, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from ..config.database import Base
from .enums import IncidentStatusEnum, SeverityEnum
from .timestamps import utcnow


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_zone", "zone"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_camera_id", "camera_id"),
        Index("ix_incidents_worker_id", "worker_id"),
        Index("ix_incidents_status", "status"),
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
    status            = Column(
        PgEnum(
            IncidentStatusEnum,
            name="incidentstatus",
            create_type=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=IncidentStatusEnum.New,
    )
    started_at        = Column(DateTime(timezone=True), nullable=True)
    validated_at      = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at   = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by   = Column(String, nullable=True)
    resolved_at       = Column(DateTime(timezone=True), nullable=True)
    resolved_by       = Column(String, nullable=True)
    archived_at       = Column(DateTime(timezone=True), nullable=True)
    sla_breached_at   = Column(DateTime(timezone=True), nullable=True)
    sla_ack_breached_at = Column(DateTime(timezone=True), nullable=True)
    sla_resolution_breached_at = Column(DateTime(timezone=True), nullable=True)
    sla_breach_count  = Column(Integer, nullable=False, default=0)
    duration_seconds  = Column(Integer, nullable=True)
    escalation_count  = Column(Integer, nullable=False, default=0)
    root_cause        = Column(Text, default="Under Investigation")
    corrective_action = Column(Text, default="Pending Review")
    created_at        = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    alerts = relationship("Alert", back_populates="incident")
