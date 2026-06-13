"""Camera ORM model."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, Index, Integer, JSON, String, Text

from ..config.database import Base


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        Index("ix_cameras_zone", "zone"),
        Index("ix_cameras_status", "status"),
    )

    id             = Column(String, primary_key=True, index=True)
    name           = Column(String, nullable=False)
    area_id        = Column(String, nullable=True)
    area_name      = Column(String, nullable=True)
    zone_id        = Column(String, nullable=True)
    zone_name      = Column(String, nullable=True)
    zone           = Column(String, nullable=False)
    url            = Column(String, nullable=True)
    stream_url     = Column(String(512), nullable=True)  # RTSP/stream source for AI detection
    source_type    = Column(String(16), nullable=True, default="rtsp")  # rtsp | mediamtx | file | webcam | webrtc
    mediamtx_path  = Column(String(128), nullable=True)
    device_index   = Column(Integer, nullable=True)
    location_description = Column(Text, nullable=True)
    supported_ai_capabilities = Column(JSON, nullable=True)
    severity_profile = Column(String, nullable=True)
    status         = Column(String, default="Online")
    is_privacy_mode = Column(Boolean, default=False)
    thumbnail      = Column(String, nullable=True)
    fps            = Column(Float, nullable=True)
    health         = Column(Float, nullable=True)
