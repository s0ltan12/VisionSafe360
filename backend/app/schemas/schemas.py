"""Pydantic schemas for request/response validation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AlertBase(BaseModel):
    type: str
    severity: str
    zone: str
    camera: str
    timestamp: str
    status: str = "New"
    description: str
    thumbnail: str
    confidence: Optional[float] = None


class AlertCreate(AlertBase):
    id: str


class AlertUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None


class AlertOut(AlertBase):
    id: str

    class Config:
        from_attributes = True


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


class IncidentBase(BaseModel):
    zone: str
    classification: str
    severity: str
    root_cause: Optional[str] = "Under Investigation"
    corrective_action: Optional[str] = "Pending Review"
    created_at: str


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


class UserBase(BaseModel):
    name: str
    email: str
    role: str
    status: str = "Active"


class UserCreate(UserBase):
    id: str
    password: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None


class UserOut(UserBase):
    id: str

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str


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