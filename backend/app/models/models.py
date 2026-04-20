"""SQLAlchemy ORM models for the active VisionSafe backend."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Column, Enum as PgEnum, Float, String, Text

from ..config.database import Base


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


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, index=True)
    type = Column(PgEnum(HazardTypeEnum, name="hazardtype"), nullable=False)
    severity = Column(PgEnum(SeverityEnum, name="severity"), nullable=False)
    zone = Column(String, nullable=False)
    camera = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
    status = Column(PgEnum(StatusEnum, name="status"), default=StatusEnum.New)
    description = Column(Text, nullable=False)
    thumbnail = Column(String, nullable=False)
    confidence = Column(Float, nullable=True)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    zone = Column(String, nullable=False)
    url = Column(String, nullable=True)
    status = Column(String, default="Online")
    is_privacy_mode = Column(Boolean, default=False)
    thumbnail = Column(String, nullable=True)
    fps = Column(Float, nullable=True)
    health = Column(Float, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, index=True)
    zone = Column(String, nullable=False)
    classification = Column(String, nullable=False)
    severity = Column(PgEnum(SeverityEnum, name="severity"), nullable=False)
    root_cause = Column(Text, default="Under Investigation")
    corrective_action = Column(Text, default="Pending Review")
    created_at = Column(String, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    role = Column(PgEnum(UserRoleEnum, name="userrole"), nullable=False)
    status = Column(String, default="Active")