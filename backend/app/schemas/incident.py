"""Incident request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ..models.enums import IncidentStatusEnum


class IncidentBase(BaseModel):
    zone: str
    classification: str
    severity: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    worker_id: Optional[str] = None
    worker_gpu_id: Optional[str] = None
    status: Optional[IncidentStatusEnum] = IncidentStatusEnum.New
    started_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    archived_at: Optional[datetime] = None
    sla_breached_at: Optional[datetime] = None
    sla_ack_breached_at: Optional[datetime] = None
    sla_resolution_breached_at: Optional[datetime] = None
    sla_breach_count: int = 0
    duration_seconds: Optional[int] = None
    escalation_count: int = 0
    root_cause: Optional[str] = "Under Investigation"
    corrective_action: Optional[str] = "Pending Review"
    created_at: Optional[datetime] = None


class IncidentCreate(IncidentBase):
    id: str


class IncidentUpdate(BaseModel):
    zone: Optional[str] = None
    classification: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[IncidentStatusEnum] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatusEnum
    note: Optional[str] = None


class IncidentOut(IncidentBase):
    id: str

    class Config:
        from_attributes = True


class IncidentEventOut(BaseModel):
    id: str
    incident_id: str
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
