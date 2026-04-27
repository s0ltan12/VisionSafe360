"""Pydantic schemas for request/response validation.

Changes from original:
- Alert: timestamp field renamed occurred_at (ISO datetime string in API)
- Incident: created_at now serialised as ISO string
- All list endpoints use PaginatedResponse[T]
- Added ErgonomicRecordOut, SystemConfigOut, NotificationOut schemas
- Added password strength validation in UserCreate
"""
from __future__ import annotations

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, field_validator

from ..utils.security import validate_password_strength

T = TypeVar("T")


# ── Pagination ────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int
    has_more: bool


# ── Alerts ────────────────────────────────────────────────────────────

class AlertBase(BaseModel):
    type: str
    severity: str
    zone: str
    camera: str
    occurred_at: Optional[datetime] = None
    status: str = "New"
    description: str
    thumbnail: Optional[str] = None
    confidence: Optional[float] = None


class AlertCreate(AlertBase):
    id: str


class AlertUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None


class AlertOut(AlertBase):
    id: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Cameras ───────────────────────────────────────────────────────────

class CameraBase(BaseModel):
    name: str
    zone: str
    url: Optional[str] = None
    status: str = "Online"
    is_privacy_mode: bool = False
    thumbnail: Optional[str] = None
    fps: Optional[float] = None
    health: Optional[float] = None


class CameraCreate(CameraBase):
    id: str


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None
    is_privacy_mode: Optional[bool] = None
    fps: Optional[float] = None
    health: Optional[float] = None


class CameraOut(CameraBase):
    id: str

    class Config:
        from_attributes = True


# ── Incidents ─────────────────────────────────────────────────────────

class IncidentBase(BaseModel):
    zone: str
    classification: str
    severity: str
    root_cause: Optional[str] = "Under Investigation"
    corrective_action: Optional[str] = "Pending Review"
    created_at: Optional[datetime] = None


class IncidentCreate(IncidentBase):
    id: str


class IncidentUpdate(BaseModel):
    zone: Optional[str] = None
    classification: Optional[str] = None
    severity: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None


class IncidentOut(IncidentBase):
    id: str

    class Config:
        from_attributes = True


# ── Users ─────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    name: str
    email: str
    role: str
    status: str = "Active"


class UserCreate(UserBase):
    id: str
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            validate_password_strength(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            validate_password_strength(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v


class UserOut(UserBase):
    id: str

    class Config:
        from_attributes = True


# ── Auth ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    role: Optional[str] = None


# ── Jobs ──────────────────────────────────────────────────────────────

class JobStartRequest(BaseModel):
    source_name: str
    camera_id: str = "cam_01"


class JobStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    source_name: Optional[str] = None
    camera_id: Optional[str] = None
    started_at: Optional[float] = None
    last_error: Optional[str] = None
    last_exit_code: Optional[int] = None


# ── Ergonomics ────────────────────────────────────────────────────────

class ErgonomicRecordCreate(BaseModel):
    id: str
    camera_id: str
    zone: Optional[str] = None
    track_id: Optional[int] = None
    risk_level: str
    rula_score: Optional[float] = None
    reba_score: Optional[float] = None
    description: Optional[str] = None
    recorded_at: Optional[datetime] = None


class ErgonomicRecordOut(BaseModel):
    id: str
    camera_id: str
    zone: Optional[str] = None
    track_id: Optional[int] = None
    risk_level: str
    rula_score: Optional[float] = None
    reba_score: Optional[float] = None
    description: Optional[str] = None
    recorded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── System Configuration ──────────────────────────────────────────────

class SystemConfigOut(BaseModel):
    key: str
    value: str
    value_type: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SystemConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None


class SystemConfigCreate(BaseModel):
    key: str
    value: str
    value_type: str = "string"
    description: Optional[str] = None


# ── Notifications ─────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    title: str
    message: str
    type: str
    is_read: bool
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    id: str
    user_id: Optional[str] = None
    title: str
    message: str
    type: str = "info"
    source: Optional[str] = None


class NotificationMarkRead(BaseModel):
    ids: List[str]