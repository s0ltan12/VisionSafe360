"""Schemas for camera safety zone geofencing."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ZoneType = Literal[
    "danger",
    "restricted",
    "forklift_only",
    "pedestrian_only",
    "no_entry",
    "loading",
    "emergency_exit",
    "custom",
]


class ZonePoint(BaseModel):
    x: float
    y: float


class SafetyZoneRule(BaseModel):
    allowed_classes: list[str] = Field(default_factory=lambda: ["person", "forklift"])
    denied_classes: list[str] = Field(default_factory=list)
    occupancy_threshold: int | None = Field(default=None, ge=1)
    dwell_time_limit_sec: float | None = Field(default=None, ge=0)
    cooldown_sec: float = Field(default=30.0, ge=0)
    min_persistence_sec: float = Field(default=0.5, ge=0)
    severity: Literal["Low", "Medium", "High", "Critical"] = "High"

    @field_validator("allowed_classes", "denied_classes")
    @classmethod
    def validate_classes(cls, value: list[str]) -> list[str]:
        allowed = {"person", "forklift"}
        cleaned = [str(item).strip().lower() for item in value if str(item).strip()]
        invalid = [item for item in cleaned if item not in allowed]
        if invalid:
            raise ValueError(f"unsupported object classes: {', '.join(invalid)}")
        return list(dict.fromkeys(cleaned))


class SafetyZoneBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    zone_type: ZoneType
    polygon: list[ZonePoint]
    coordinate_space: str = "source_pixels"
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    color: str = Field(default="#f97316", pattern=r"^#[0-9A-Fa-f]{6}$")
    enabled: bool = True
    priority: int = 100
    rules: SafetyZoneRule = Field(default_factory=SafetyZoneRule)
    description: str | None = None

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, value: list[ZonePoint]) -> list[ZonePoint]:
        if len(value) < 3:
            raise ValueError("polygon requires at least 3 points")
        return value


class SafetyZoneCreate(SafetyZoneBase):
    id: str | None = None


class SafetyZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    zone_type: ZoneType | None = None
    polygon: list[ZonePoint] | None = None
    coordinate_space: str | None = None
    source_width: int | None = Field(default=None, gt=0)
    source_height: int | None = Field(default=None, gt=0)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    enabled: bool | None = None
    priority: int | None = None
    rules: SafetyZoneRule | None = None
    description: str | None = None

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, value: list[ZonePoint] | None) -> list[ZonePoint] | None:
        if value is not None and len(value) < 3:
            raise ValueError("polygon requires at least 3 points")
        return value


class SafetyZoneEnabledUpdate(BaseModel):
    enabled: bool


class SafetyZoneOut(SafetyZoneBase):
    id: str
    camera_id: str
    created_by_id: str | None = None
    updated_by_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SafetyZoneEventOut(BaseModel):
    id: str
    zone_id: str
    camera_id: str
    event_type: str
    object_class: str
    track_id: int | None = None
    stable_object_key: str
    severity: str
    occurred_at: datetime
    duration_inside_sec: int | None = None
    occupancy_count: int | None = None
    frame_number: int | None = None
    bbox: Any | None = None
    anchor_point: Any | None = None
    event_metadata: dict | None = None
    alert_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SafetyZoneStatsOut(BaseModel):
    zone_id: str
    camera_id: str
    event_count: int
    violation_count: int
    current_occupancy: int
    avg_dwell_time_sec: float
    max_dwell_time_sec: float
    last_event_at: datetime | None = None
