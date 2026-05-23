"""Alert request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AlertBase(BaseModel):
    type: str
    severity: str
    zone: str
    area_id: Optional[str] = None
    area_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    location_description: Optional[str] = None
    camera: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    worker_id: Optional[str] = None
    worker_gpu_id: Optional[str] = None
    occurred_at: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("occurred_at", "timestamp"),
    )
    status: str = "New"
    description: str
    thumbnail: Optional[str] = None
    confidence: Optional[float] = None
    acknowledged_by: Optional[str] = None
    acknowledged_by_id: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_by_id: Optional[str] = None
    resolved_at: Optional[datetime] = None
    archived_by: Optional[str] = None
    archived_by_id: Optional[str] = None
    archived_at: Optional[datetime] = None
    false_positive_by: Optional[str] = None
    false_positive_by_id: Optional[str] = None
    false_positive_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)


class AlertCreate(AlertBase):
    id: str


class AlertUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None


class AlertOut(AlertBase):
    id: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertEventOut(BaseModel):
    id: str
    alert_id: str
    action: str
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    note: Optional[str] = None
    event_metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
