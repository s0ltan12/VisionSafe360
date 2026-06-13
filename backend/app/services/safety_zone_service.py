"""Business logic for camera safety zone geofencing."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Camera, CameraSafetyZone, CameraSafetyZoneEvent
from ..schemas.safety_zone import (
    SafetyZoneCreate,
    SafetyZoneEnabledUpdate,
    SafetyZoneUpdate,
)


def _dump_rules(rules: Any) -> dict:
    if rules is None:
        return {}
    if hasattr(rules, "model_dump"):
        return rules.model_dump()
    return dict(rules)


def _dump_polygon(polygon: Any) -> list[dict]:
    return [
        point.model_dump() if hasattr(point, "model_dump") else {"x": point["x"], "y": point["y"]}
        for point in polygon
    ]


class SafetyZoneService:
    @staticmethod
    def list_for_camera(db: Session, camera_id: str, *, include_disabled: bool = True) -> list[CameraSafetyZone]:
        query = db.query(CameraSafetyZone).filter(
            CameraSafetyZone.camera_id == camera_id,
            CameraSafetyZone.deleted_at.is_(None),
        )
        if not include_disabled:
            query = query.filter(CameraSafetyZone.enabled.is_(True))
        return query.order_by(CameraSafetyZone.priority.asc(), CameraSafetyZone.name.asc()).all()

    @staticmethod
    def get(db: Session, zone_id: str) -> CameraSafetyZone | None:
        return db.query(CameraSafetyZone).filter(
            CameraSafetyZone.id == zone_id,
            CameraSafetyZone.deleted_at.is_(None),
        ).first()

    @staticmethod
    def create(
        db: Session,
        camera_id: str,
        payload: SafetyZoneCreate,
        *,
        actor_id: str | None = None,
    ) -> CameraSafetyZone:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        zone = CameraSafetyZone(
            id=payload.id or f"CSZ-{uuid.uuid4().hex[:12]}",
            camera_id=camera_id,
            name=payload.name,
            zone_type=payload.zone_type,
            polygon=_dump_polygon(payload.polygon),
            coordinate_space=payload.coordinate_space,
            source_width=payload.source_width,
            source_height=payload.source_height,
            color=payload.color,
            enabled=payload.enabled,
            priority=payload.priority,
            rules=_dump_rules(payload.rules),
            description=payload.description,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        db.add(zone)
        db.commit()
        db.refresh(zone)
        return zone

    @staticmethod
    def update(
        db: Session,
        zone_id: str,
        payload: SafetyZoneUpdate,
        *,
        actor_id: str | None = None,
    ) -> CameraSafetyZone | None:
        zone = SafetyZoneService.get(db, zone_id)
        if zone is None:
            return None
        changes = payload.model_dump(exclude_unset=True)
        if "polygon" in changes and payload.polygon is not None:
            changes["polygon"] = _dump_polygon(payload.polygon)
        if "rules" in changes and payload.rules is not None:
            changes["rules"] = _dump_rules(payload.rules)
        for field, value in changes.items():
            setattr(zone, field, value)
        zone.updated_by_id = actor_id
        db.commit()
        db.refresh(zone)
        return zone

    @staticmethod
    def set_enabled(
        db: Session,
        zone_id: str,
        payload: SafetyZoneEnabledUpdate,
        *,
        actor_id: str | None = None,
    ) -> CameraSafetyZone | None:
        zone = SafetyZoneService.get(db, zone_id)
        if zone is None:
            return None
        zone.enabled = payload.enabled
        zone.updated_by_id = actor_id
        db.commit()
        db.refresh(zone)
        return zone

    @staticmethod
    def delete(db: Session, zone_id: str, *, actor_id: str | None = None) -> bool:
        zone = SafetyZoneService.get(db, zone_id)
        if zone is None:
            return False
        zone.deleted_at = datetime.now(timezone.utc)
        zone.updated_by_id = actor_id
        db.commit()
        return True

    @staticmethod
    def list_events(
        db: Session,
        *,
        zone_id: str | None = None,
        camera_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CameraSafetyZoneEvent]:
        query = db.query(CameraSafetyZoneEvent)
        if zone_id:
            query = query.filter(CameraSafetyZoneEvent.zone_id == zone_id)
        if camera_id:
            query = query.filter(CameraSafetyZoneEvent.camera_id == camera_id)
        return query.order_by(CameraSafetyZoneEvent.occurred_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def stats_for_zone(db: Session, zone_id: str) -> dict:
        zone = SafetyZoneService.get(db, zone_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Safety zone not found")
        return SafetyZoneService._stats(db, zone_id=zone.id, camera_id=zone.camera_id)

    @staticmethod
    def stats_for_camera(db: Session, camera_id: str) -> list[dict]:
        return [
            SafetyZoneService._stats(db, zone_id=zone.id, camera_id=camera_id)
            for zone in SafetyZoneService.list_for_camera(db, camera_id)
        ]

    @staticmethod
    def edge_config(db: Session, camera_id: str) -> dict:
        zones = SafetyZoneService.list_for_camera(db, camera_id, include_disabled=False)
        latest_revision = max((zone.updated_at or zone.created_at for zone in zones), default=None)
        return {
            "camera_id": camera_id,
            "revision": latest_revision.isoformat() if latest_revision else None,
            "zones": [
                {
                    "id": zone.id,
                    "name": zone.name,
                    "zone_type": zone.zone_type,
                    "polygon": zone.polygon,
                    "coordinate_space": zone.coordinate_space,
                    "source_width": zone.source_width,
                    "source_height": zone.source_height,
                    "color": zone.color,
                    "enabled": zone.enabled,
                    "priority": zone.priority,
                    "rules": zone.rules or {},
                }
                for zone in zones
            ],
        }

    @staticmethod
    def record_event(
        db: Session,
        *,
        zone_id: str,
        camera_id: str,
        event_type: str,
        object_class: str,
        track_id: int | None,
        stable_object_key: str,
        severity: str,
        occurred_at,
        duration_inside_sec: float | None = None,
        occupancy_count: int | None = None,
        frame_number: int | None = None,
        bbox: Any | None = None,
        anchor_point: Any | None = None,
        metadata: dict | None = None,
        alert_id: str | None = None,
    ) -> CameraSafetyZoneEvent:
        event = CameraSafetyZoneEvent(
            id=f"ZEV-{uuid.uuid4().hex[:12]}",
            zone_id=zone_id,
            camera_id=camera_id,
            event_type=event_type,
            object_class=object_class,
            track_id=track_id,
            stable_object_key=stable_object_key,
            severity=severity,
            occurred_at=occurred_at,
            duration_inside_sec=float(duration_inside_sec) if duration_inside_sec is not None else None,
            occupancy_count=occupancy_count,
            frame_number=frame_number,
            bbox=bbox,
            anchor_point=anchor_point,
            event_metadata=metadata,
            alert_id=alert_id,
        )
        db.add(event)
        return event

    @staticmethod
    def _stats(db: Session, *, zone_id: str, camera_id: str) -> dict:
        base = db.query(CameraSafetyZoneEvent).filter(CameraSafetyZoneEvent.zone_id == zone_id)
        event_count = base.count()
        violation_count = base.filter(CameraSafetyZoneEvent.event_type.ilike("%violation%")).count()
        last_event_at = db.query(func.max(CameraSafetyZoneEvent.occurred_at)).filter(
            CameraSafetyZoneEvent.zone_id == zone_id
        ).scalar()
        avg_dwell = db.query(func.avg(CameraSafetyZoneEvent.duration_inside_sec)).filter(
            CameraSafetyZoneEvent.zone_id == zone_id,
            CameraSafetyZoneEvent.duration_inside_sec.isnot(None),
        ).scalar()
        max_dwell = db.query(func.max(CameraSafetyZoneEvent.duration_inside_sec)).filter(
            CameraSafetyZoneEvent.zone_id == zone_id,
            CameraSafetyZoneEvent.duration_inside_sec.isnot(None),
        ).scalar()
        latest_enter = base.filter(CameraSafetyZoneEvent.event_type == "enter").count()
        latest_exit = base.filter(CameraSafetyZoneEvent.event_type == "exit").count()
        return {
            "zone_id": zone_id,
            "camera_id": camera_id,
            "event_count": event_count,
            "violation_count": violation_count,
            "current_occupancy": max(0, latest_enter - latest_exit),
            "avg_dwell_time_sec": round(float(avg_dwell or 0.0), 1),
            "max_dwell_time_sec": round(float(max_dwell or 0.0), 1),
            "last_event_at": last_event_at,
        }
