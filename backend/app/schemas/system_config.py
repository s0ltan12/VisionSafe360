"""Runtime system configuration schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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
