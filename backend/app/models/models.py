"""SQLAlchemy ORM models for VisionSafe 360.

Changes from original:
- Timestamps changed from Column(String) to Column(DateTime(timezone=True))
- Added database indexes on frequently queried columns
- Added ErgonomicRecord, SystemConfig, Notification models
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as PgEnum,
    Float, Index, Integer, String, Text,
)

from ..config.database import Base


# ── Enumerations ─────────────────────────────────────────────────────

class SeverityEnum(str, enum.Enum):
    High = "High"
    Medium = "Medium"
    Low = "Low"


class StatusEnum(str, enum.Enum):
    New = "New"
    Notified = "Notified"
    Acknowledged = "Acknowledged"
    In_Investigation = "In Investigation"
    Resolved = "Resolved"
    Dismissed = "Dismissed"
    Active = "Active"


class HazardTypeEnum(str, enum.Enum):
    PPE = "PPE"
    Fall = "Fall"
    Proximity = "Proximity"
    Ergonomics = "Ergonomics"
    Intrusion = "Intrusion"


class UserRoleEnum(str, enum.Enum):
    Admin = "Admin"
    Safety_Engineer = "Safety Engineer"
    Data_Analyst = "Data Analyst"


class RiskLevelEnum(str, enum.Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Critical = "Critical"


# ── Helpers ──────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Models ───────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_type", "type"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_zone", "zone"),
        Index("ix_alerts_camera_id", "camera_id"),
        Index("ix_alerts_worker_id", "worker_id"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_occurred_at", "occurred_at"),
    )

    id          = Column(String, primary_key=True, index=True)
    type        = Column(PgEnum(HazardTypeEnum, name="hazardtype", create_type=False), nullable=False)
    severity    = Column(PgEnum(SeverityEnum,   name="severity",   create_type=False), nullable=False)
    zone        = Column(String, nullable=False)
    camera      = Column(String, nullable=False)
    camera_id   = Column(String, nullable=True)
    camera_name = Column(String, nullable=True)
    worker_id   = Column(String, nullable=True)
    worker_gpu_id = Column(String, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status      = Column(PgEnum(StatusEnum, name="status", create_type=False), default=StatusEnum.New)
    description = Column(Text, nullable=False)
    thumbnail   = Column(String, nullable=True)
    confidence  = Column(Float, nullable=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        Index("ix_cameras_zone", "zone"),
        Index("ix_cameras_status", "status"),
    )

    id             = Column(String, primary_key=True, index=True)
    name           = Column(String, nullable=False)
    zone           = Column(String, nullable=False)
    url            = Column(String, nullable=True)
    stream_url     = Column(String(512), nullable=True)  # RTSP/stream source for AI detection
    status         = Column(String, default="Online")
    is_privacy_mode = Column(Boolean, default=False)
    thumbnail      = Column(String, nullable=True)
    fps            = Column(Float, nullable=True)
    health         = Column(Float, nullable=True)


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
    created_at        = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    role          = Column(PgEnum(UserRoleEnum, name="userrole", create_type=False), nullable=False)
    status        = Column(String, default="Active")
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ErgonomicRecord(Base):
    """Stores ergonomic risk assessment results from the edge AI pipeline."""
    __tablename__ = "ergonomic_records"
    __table_args__ = (
        Index("ix_ergo_camera_id", "camera_id"),
        Index("ix_ergo_risk_level", "risk_level"),
        Index("ix_ergo_recorded_at", "recorded_at"),
    )

    id          = Column(String, primary_key=True, index=True)
    camera_id   = Column(String, nullable=False)
    zone        = Column(String, nullable=True)
    track_id    = Column(Integer, nullable=True)
    risk_level  = Column(PgEnum(RiskLevelEnum, name="risklevel"), nullable=False)
    rula_score  = Column(Float, nullable=True)
    reba_score  = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class SystemConfig(Base):
    """Key-value store for runtime system configuration."""
    __tablename__ = "system_config"

    key        = Column(String, primary_key=True, index=True)
    value      = Column(Text, nullable=False)
    value_type = Column(String, nullable=False, default="string")  # string|bool|int|float|json
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class Notification(Base):
    """System notifications delivered to the dashboard in real-time."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notif_user_id", "user_id"),
        Index("ix_notif_read", "is_read"),
        Index("ix_notif_created_at", "created_at"),
    )

    id         = Column(String, primary_key=True, index=True)
    user_id    = Column(String, nullable=True)   # None = broadcast to all
    title      = Column(String, nullable=False)
    message    = Column(Text, nullable=False)
    type       = Column(String, nullable=False, default="info")  # info|alert|system
    is_read    = Column(Boolean, default=False)
    source     = Column(String, nullable=True)   # e.g. "edge_ai", "system", "user"
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
