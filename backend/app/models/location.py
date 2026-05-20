"""Area and Zone — operational location hierarchy inside the facility."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, String, Text

from ..config.database import Base
from .timestamps import utcnow


class Area(Base):
    """Operational area inside the monitored facility."""
    __tablename__ = "areas"
    __table_args__ = (
        Index("ix_areas_name", "name"),
        Index("ix_areas_risk_level", "risk_level"),
    )

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    risk_level = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Zone(Base):
    """Safety zone within an operational area."""
    __tablename__ = "zones"
    __table_args__ = (
        Index("ix_zones_area_id", "area_id"),
        Index("ix_zones_name", "name"),
        Index("ix_zones_risk_level", "risk_level"),
    )

    id = Column(String, primary_key=True, index=True)
    area_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    risk_level = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
