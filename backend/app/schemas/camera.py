"""Camera request/response schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CameraBase(BaseModel):
    name: str
    zone: str
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    url: Optional[str] = None
    stream_url: Optional[str] = None  # RTSP/stream source for AI detection
    location_description: Optional[str] = None
    supported_ai_capabilities: Optional[list[str]] = None
    severity_profile: Optional[str] = None
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
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    url: Optional[str] = None
    stream_url: Optional[str] = None  # RTSP/stream source for AI detection
    location_description: Optional[str] = None
    supported_ai_capabilities: Optional[list[str]] = None
    severity_profile: Optional[str] = None
    status: Optional[str] = None
    is_privacy_mode: Optional[bool] = None
    fps: Optional[float] = None
    health: Optional[float] = None


class CameraOut(CameraBase):
    id: str

    class Config:
        from_attributes = True
