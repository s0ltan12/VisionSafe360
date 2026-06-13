"""Camera-view polygon safety zones and zone interaction history."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text

from ..config.database import Base
from .timestamps import utcnow


class CameraSafetyZone(Base):
    """Polygon geofence drawn in one camera's source pixel coordinate space."""

    __tablename__ = "camera_safety_zones"
    __table_args__ = (
        Index("ix_camera_safety_zones_camera_enabled", "camera_id", "enabled"),
        Index("ix_camera_safety_zones_camera_type", "camera_id", "zone_type"),
        Index("ix_camera_safety_zones_deleted_at", "deleted_at"),
    )

    id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    name = Column(String, nullable=False)
    zone_type = Column(String, nullable=False)
    polygon = Column(JSON, nullable=False)
    coordinate_space = Column(String, nullable=False, default="source_pixels")
    source_width = Column(Integer, nullable=False)
    source_height = Column(Integer, nullable=False)
    color = Column(String, nullable=False, default="#f97316")
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    rules = Column(JSON, nullable=False, default=dict)
    description = Column(Text, nullable=True)
    created_by_id = Column(String, nullable=True)
    updated_by_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class CameraSafetyZoneEvent(Base):
    """Append-only event history for zone interactions and violations."""

    __tablename__ = "camera_safety_zone_events"
    __table_args__ = (
        Index("ix_camera_safety_zone_events_camera_time", "camera_id", "occurred_at"),
        Index("ix_camera_safety_zone_events_zone_time", "zone_id", "occurred_at"),
        Index("ix_camera_safety_zone_events_type_time", "event_type", "occurred_at"),
        Index("ix_camera_safety_zone_events_stable_object_time", "stable_object_key", "occurred_at"),
    )

    id = Column(String, primary_key=True, index=True)
    zone_id = Column(String, ForeignKey("camera_safety_zones.id"), nullable=False)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    event_type = Column(String, nullable=False)
    object_class = Column(String, nullable=False)
    track_id = Column(Integer, nullable=True)
    stable_object_key = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    duration_inside_sec = Column(Float, nullable=True)
    occupancy_count = Column(Integer, nullable=True)
    frame_number = Column(Integer, nullable=True)
    bbox = Column(JSON, nullable=True)
    anchor_point = Column(JSON, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    alert_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
