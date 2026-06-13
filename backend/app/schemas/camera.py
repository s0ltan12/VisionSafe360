"""Camera request/response schemas."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class CameraBase(BaseModel):
    name: str
    zone: str
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    url: Optional[str] = None
    stream_url: Optional[str] = None  # RTSP/stream source for AI detection
    source_type: Optional[str] = "rtsp"  # rtsp | mediamtx | file | webcam | webrtc
    mediamtx_path: Optional[str] = None
    device_index: Optional[int] = None
    location_description: Optional[str] = None
    supported_ai_capabilities: Optional[list[str]] = None
    severity_profile: Optional[str] = None
    status: str = "Online"
    is_privacy_mode: bool = False
    thumbnail: Optional[str] = None
    fps: Optional[float] = None
    health: Optional[float] = None


def _new_camera_id() -> str:
    return f"CAM-{uuid4().hex[:6].upper()}"


class CameraCreate(CameraBase):
    id: str = Field(default_factory=_new_camera_id)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_blank_id(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return _new_camera_id()
        return value


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    url: Optional[str] = None
    stream_url: Optional[str] = None  # RTSP/stream source for AI detection
    source_type: Optional[str] = None
    mediamtx_path: Optional[str] = None
    device_index: Optional[int] = None
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
