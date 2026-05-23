"""Dashboard notification schemas."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


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
