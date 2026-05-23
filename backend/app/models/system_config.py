"""SystemConfig ORM model — runtime key-value configuration store."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text

from ..config.database import Base
from .timestamps import utcnow


class SystemConfig(Base):
    """Key-value store for runtime system configuration."""
    __tablename__ = "system_config"

    key        = Column(String, primary_key=True, index=True)
    value      = Column(Text, nullable=False)
    value_type = Column(String, nullable=False, default="string")  # string|bool|int|float|json
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
