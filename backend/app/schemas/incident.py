"""Incident request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IncidentBase(BaseModel):
    zone: str
    classification: str
    severity: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    worker_id: Optional[str] = None
    worker_gpu_id: Optional[str] = None
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
