"""Alert and alert-lifecycle event ORM models."""
from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, Enum as PgEnum, Float, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import relationship

from ..config.database import Base
from .enums import HazardTypeEnum, SeverityEnum, StatusEnum
from .timestamps import utcnow


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_type", "type"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_zone", "zone"),
        Index("ix_alerts_area_id", "area_id"),
        Index("ix_alerts_zone_id", "zone_id"),
        Index("ix_alerts_camera_id", "camera_id"),
        Index("ix_alerts_worker_id", "worker_id"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_occurred_at", "occurred_at"),
        Index("ix_alerts_incident_id", "incident_id"),
    )

    id          = Column(String, primary_key=True, index=True)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=True)
    type        = Column(PgEnum(HazardTypeEnum, name="hazardtype", create_type=False), nullable=False)
    severity    = Column(PgEnum(SeverityEnum,   name="severity",   create_type=False), nullable=False)
    zone        = Column(String, nullable=False)
    area_id     = Column(String, nullable=True)
    area_name   = Column(String, nullable=True)
    zone_id     = Column(String, nullable=True)
    zone_name   = Column(String, nullable=True)
    location_description = Column(Text, nullable=True)
    camera      = Column(String, nullable=False)
    camera_id   = Column(String, nullable=True)
    camera_name = Column(String, nullable=True)
    worker_id   = Column(String, nullable=True)
    worker_gpu_id = Column(String, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    status      = Column(
        PgEnum(
            StatusEnum,
            name="status",
            create_type=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=StatusEnum.New,
    )
    description = Column(Text, nullable=False)
    thumbnail   = Column(String, nullable=True)
    event_frame = Column(Text, nullable=True)
    video_evidence = Column(Text, nullable=True)
    track_id = Column(Integer, nullable=True)
    frame_number = Column(Integer, nullable=True)
    frame_width = Column(Integer, nullable=True)
    frame_height = Column(Integer, nullable=True)
    evidence_kind = Column(String, nullable=True)
    confidence  = Column(Float, nullable=True)
    acknowledged_by = Column(String, nullable=True)
    acknowledged_by_id = Column(String, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, nullable=True)
    resolved_by_id = Column(String, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    archived_by = Column(String, nullable=True)
    archived_by_id = Column(String, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    false_positive_by = Column(String, nullable=True)
    false_positive_by_id = Column(String, nullable=True)
    false_positive_at = Column(DateTime(timezone=True), nullable=True)
    event_metadata = Column(JSON, nullable=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    incident = relationship("Incident", back_populates="alerts")


class AlertEvent(Base):
    """Append-only alert lifecycle timeline entry."""
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_alert_id", "alert_id"),
        Index("ix_alert_events_created_at", "created_at"),
    )

    id = Column(String, primary_key=True, index=True)
    alert_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    actor_id = Column(String, nullable=True)
    actor_name = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
