"""Enumerations shared across ORM models and Pydantic schemas."""
from __future__ import annotations

import enum


class SeverityEnum(str, enum.Enum):
    Critical = "Critical"
    High = "High"
    Medium = "Medium"
    Low = "Low"


class StatusEnum(str, enum.Enum):
    New = "New"
    Notified = "Notified"
    Acknowledged = "Acknowledged"
    In_Investigation = "In Investigation"
    Resolved = "Resolved"
    Archived = "Archived"
    False_Positive = "False Positive"
    Dismissed = "Dismissed"
    Active = "Active"


class IncidentStatusEnum(str, enum.Enum):
    New = "New"
    Validating = "Validating"
    Active = "Active"
    Acknowledged = "Acknowledged"
    Resolved = "Resolved"
    False_Positive = "False Positive"
    Archived = "Archived"


class HazardTypeEnum(str, enum.Enum):
    PPE = "PPE"
    Fall = "Fall"
    Proximity = "Proximity"
    Overspeed = "Overspeed"
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
