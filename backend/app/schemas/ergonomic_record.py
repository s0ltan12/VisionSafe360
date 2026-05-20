"""Ergonomic record schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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
