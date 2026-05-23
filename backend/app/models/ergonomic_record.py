"""ErgonomicRecord ORM model — RULA/REBA risk assessment results."""
from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, Enum as PgEnum, Float, Index, Integer, String, Text,
)

from ..config.database import Base
from .enums import RiskLevelEnum
from .timestamps import utcnow


class ErgonomicRecord(Base):
    """Stores ergonomic risk assessment results from the edge AI pipeline."""
    __tablename__ = "ergonomic_records"
    __table_args__ = (
        Index("ix_ergo_camera_id", "camera_id"),
        Index("ix_ergo_risk_level", "risk_level"),
        Index("ix_ergo_recorded_at", "recorded_at"),
    )

    id          = Column(String, primary_key=True, index=True)
    camera_id   = Column(String, nullable=False)
    zone        = Column(String, nullable=True)
    track_id    = Column(Integer, nullable=True)
    risk_level  = Column(PgEnum(RiskLevelEnum, name="risklevel"), nullable=False)
    rula_score  = Column(Float, nullable=True)
    reba_score  = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
