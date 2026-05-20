"""Notification ORM model — real-time dashboard notifications."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text

from ..config.database import Base
from .timestamps import utcnow


class Notification(Base):
    """System notifications delivered to the dashboard in real-time."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notif_user_id", "user_id"),
        Index("ix_notif_read", "is_read"),
        Index("ix_notif_created_at", "created_at"),
    )

    id         = Column(String, primary_key=True, index=True)
    user_id    = Column(String, nullable=True)   # None = broadcast to all
    title      = Column(String, nullable=False)
    message    = Column(Text, nullable=False)
    type       = Column(String, nullable=False, default="info")  # info|alert|system
    is_read    = Column(Boolean, default=False)
    source     = Column(String, nullable=True)   # e.g. "edge_ai", "system", "user"
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
