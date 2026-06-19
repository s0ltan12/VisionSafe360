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
from ..utils.ppe import normalize_required_ppe

SUPPORTED_ZONE_CLASSES = ("person", "forklift")
PPE_ZONE_TYPES = {"ppe", "ppe_required"}

DEFAULT_ZONE_CONFIG: dict[str, dict[str, Any]] = {
    "danger": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": 0,
        "dwell_time_limit_sec": 3,
        "cooldown_sec": 5,
        "min_persistence_sec": 0.5,
        "severity": "Critical",
    },
    "no_entry": {
        "allowed_classes": [],
        "denied_classes": ["person", "forklift"],
        "required_ppe": [],
        "occupancy_threshold": 0,
        "dwell_time_limit_sec": 0,
        "cooldown_sec": 0,
        "min_persistence_sec": 0.5,
        "severity": "Critical",
    },
    "forklift_only": {
        "allowed_classes": ["forklift"],
        "denied_classes": ["person"],
        "required_ppe": [],
        "occupancy_threshold": 1,
        "dwell_time_limit_sec": 0,
        "cooldown_sec": 10,
        "min_persistence_sec": 0.5,
        "severity": "High",
    },
    "pedestrian_only": {
        "allowed_classes": ["person"],
        "denied_classes": ["forklift"],
        "required_ppe": [],
        "occupancy_threshold": None,
        "dwell_time_limit_sec": 0,
        "cooldown_sec": 15,
        "min_persistence_sec": 0.5,
        "severity": "High",
    },
    "restricted": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": None,
        "dwell_time_limit_sec": 30,
        "cooldown_sec": 30,
        "min_persistence_sec": 0.5,
        "severity": "Medium",
    },
    "loading": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": None,
        "dwell_time_limit_sec": 10,
        "cooldown_sec": 20,
        "min_persistence_sec": 0.5,
        "severity": "High",
    },
    "emergency_exit": {
        "allowed_classes": [],
        "denied_classes": ["person", "forklift"],
        "required_ppe": [],
        "occupancy_threshold": 0,
        "dwell_time_limit_sec": 0,
        "cooldown_sec": 0,
        "min_persistence_sec": 0.5,
        "severity": "Critical",
    },
    "ppe": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": None,
        "dwell_time_limit_sec": 15,
        "cooldown_sec": 25,
        "min_persistence_sec": 0.5,
        "severity": "Medium",
    },
    "ppe_required": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": None,
        "dwell_time_limit_sec": 15,
        "cooldown_sec": 25,
        "min_persistence_sec": 0.5,
        "severity": "Medium",
    },
    "maintenance": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": 4,
        "dwell_time_limit_sec": 60,
        "cooldown_sec": 30,
        "min_persistence_sec": 0.5,
        "severity": "Medium",
    },
    "custom": {
        "allowed_classes": ["person", "forklift"],
        "denied_classes": [],
        "required_ppe": [],
        "occupancy_threshold": None,
        "dwell_time_limit_sec": 10,
        "cooldown_sec": 30,
        "min_persistence_sec": 0.5,
        "severity": "Medium",
    },
}

LOCKED_ZONE_TYPES = {zone_type for zone_type in DEFAULT_ZONE_CONFIG if zone_type != "custom"}
FULL_DENY_ZONE_TYPES = {"no_entry", "emergency_exit"}
_REQUIRED_PPE_UNSET = object()


def _dump_rules(rules: Any) -> dict:
    if rules is None:
        return {}
    if hasattr(rules, "model_dump"):
        return rules.model_dump()
    return dict(rules)


def _copy_default_rules(zone_type: str) -> dict:
    defaults = DEFAULT_ZONE_CONFIG.get(zone_type)
    if defaults is None:
        raise HTTPException(status_code=422, detail=f"Unsupported safety zone type: {zone_type}")
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in defaults.items()
    }


def _normalize_rules(raw_rules: Any) -> dict:
    rules = {**_copy_default_rules("custom"), **_dump_rules(raw_rules)}
    allowed = [str(item).strip().lower() for item in rules.get("allowed_classes") or [] if str(item).strip()]
    denied = [str(item).strip().lower() for item in rules.get("denied_classes") or [] if str(item).strip()]
    invalid = sorted((set(allowed) | set(denied)) - set(SUPPORTED_ZONE_CLASSES))
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported object classes: {', '.join(invalid)}")

    allowed = list(dict.fromkeys(allowed))
    explicit_denied = list(dict.fromkeys(denied))
    denied = list(dict.fromkeys([*explicit_denied, *(item for item in SUPPORTED_ZONE_CLASSES if item not in allowed)]))

    occupancy_threshold = rules.get("occupancy_threshold")
    if occupancy_threshold in ("", None):
        occupancy_threshold = None
    else:
        occupancy_threshold = int(occupancy_threshold)
        if occupancy_threshold < 0:
            raise HTTPException(status_code=422, detail="occupancy_threshold must be greater than or equal to 0")

    dwell_time_limit_sec = rules.get("dwell_time_limit_sec")
    if dwell_time_limit_sec in ("", None):
        dwell_time_limit_sec = None
    else:
        dwell_time_limit_sec = float(dwell_time_limit_sec)
        if dwell_time_limit_sec < 0:
            raise HTTPException(status_code=422, detail="dwell_time_limit_sec must be greater than or equal to 0")

    cooldown_sec = float(rules.get("cooldown_sec", 30))
    min_persistence_sec = float(rules.get("min_persistence_sec", 0.5))
    if cooldown_sec < 0:
        raise HTTPException(status_code=422, detail="cooldown_sec must be greater than or equal to 0")
    if min_persistence_sec < 0:
        raise HTTPException(status_code=422, detail="min_persistence_sec must be greater than or equal to 0")

    severity = str(rules.get("severity") or "Medium").strip().title()
    if severity not in {"Low", "Medium", "High", "Critical"}:
        raise HTTPException(status_code=422, detail="severity must be Low, Medium, High, or Critical")

    try:
        required_ppe = normalize_required_ppe(rules.get("required_ppe") or rules.get("requiredPpe") or [])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "allowed_classes": allowed,
        "denied_classes": denied,
        "required_ppe": required_ppe,
        "occupancy_threshold": occupancy_threshold,
        "dwell_time_limit_sec": dwell_time_limit_sec,
        "cooldown_sec": cooldown_sec,
        "min_persistence_sec": min_persistence_sec,
        "severity": severity,
    }


def _rules_with_required_ppe(raw_rules: Any, required_ppe: Any = _REQUIRED_PPE_UNSET) -> dict:
    rules = _dump_rules(raw_rules)
    if required_ppe is not _REQUIRED_PPE_UNSET:
        rules["required_ppe"] = required_ppe or []
    return rules


def resolve_zone_rules(zone_type: str, raw_rules: Any = None) -> dict:
    if zone_type in LOCKED_ZONE_TYPES:
        if zone_type in PPE_ZONE_TYPES:
            raw = _dump_rules(raw_rules)
            try:
                return _normalize_rules(
                    {
                        **_copy_default_rules(zone_type),
                        **raw,
                        "required_ppe": raw.get("required_ppe") or raw.get("requiredPpe") or [],
                    }
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _copy_default_rules(zone_type)

    rules = _normalize_rules(raw_rules)
    if not rules["allowed_classes"] and zone_type not in FULL_DENY_ZONE_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Denying both people and forklifts is only allowed for No Entry and Emergency Exit zones",
        )
    return rules


def _dump_polygon(polygon: Any) -> list[dict]:
    return [
        point.model_dump() if hasattr(point, "model_dump") else {"x": point["x"], "y": point["y"]}
        for point in polygon
    ]


def _compact_event_metadata(metadata: Any) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    bulky_keys = {
        "event_frame_data_url",
        "snapshot_data_url",
        "clip_thumbnail_data_url",
        "video_evidence_data_url",
    }
    return {key: value for key, value in metadata.items() if key not in bulky_keys}


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
        resolved_rules = resolve_zone_rules(
            payload.zone_type,
            _rules_with_required_ppe(
                payload.rules,
                payload.required_ppe if payload.required_ppe is not None else _REQUIRED_PPE_UNSET,
            ),
        )
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
            rules=resolved_rules,
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
        next_zone_type = str(changes.get("zone_type") or zone.zone_type)
        if "zone_type" in changes or "rules" in changes or "required_ppe" in changes:
            required_ppe = (
                changes.pop("required_ppe")
                if "required_ppe" in changes
                else _REQUIRED_PPE_UNSET
            )
            submitted_rules = _rules_with_required_ppe(
                payload.rules if "rules" in changes else zone.rules,
                required_ppe,
            )
            changes["rules"] = resolve_zone_rules(next_zone_type, submitted_rules)
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
        events = query.order_by(CameraSafetyZoneEvent.occurred_at.desc()).offset(skip).limit(limit).all()
        for event in events:
            event.event_metadata = _compact_event_metadata(event.event_metadata)
        return events

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
                    "rules": resolve_zone_rules(str(zone.zone_type), zone.rules),
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
