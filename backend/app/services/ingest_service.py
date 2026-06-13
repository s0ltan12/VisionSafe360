"""Ingest service — converts raw edge AI hazard events into DB rows.

Called exclusively by the /ingest/incident route. Handles:
  - Payload format detection (raw HazardEvent vs pre-converted)
  - Severity + hazard-type mapping
  - Camera / area / zone resolution
  - Incident, Alert, and ErgonomicRecord persistence
  - Duplicate detection
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    Alert,
    AlertEvent,
    Area,
    Camera,
    CameraSafetyZone,
    ErgonomicRecord,
    HazardTypeEnum,
    Incident,
    IncidentEvent,
    IncidentStatusEnum,
    Notification,
    RiskLevelEnum,
    SeverityEnum,
    StatusEnum,
    Zone,
)
from ..schemas.ingest import HazardEventPayload
from .alert_service import AlertService
from .evidence_service import EvidenceService
from .incident_timeline_service import IncidentTimelineService
from .notification_dispatch_service import NotificationDispatchService
from .safety_zone_service import SafetyZoneService

logger = logging.getLogger("visionsafe.ingest")

# ── Lookup maps ───────────────────────────────────────────────────────


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

_SEVERITY_MAP: dict[str, SeverityEnum] = {
    "CRITICAL": SeverityEnum.Critical,
    "HIGH":     SeverityEnum.High,
    "MEDIUM":   SeverityEnum.Medium,
    "LOW":      SeverityEnum.Low,
}

_HAZARD_TYPE_MAP: dict[str, HazardTypeEnum] = {
    "fall_confirmed":             HazardTypeEnum.Fall,
    "fall_candidate":             HazardTypeEnum.Fall,
    "forklift_overspeed":         HazardTypeEnum.Overspeed,
    "forklift_proximity":         HazardTypeEnum.Proximity,
    "forklift_proximity_danger":  HazardTypeEnum.Proximity,
    "forklift_proximity_warning": HazardTypeEnum.Proximity,
    "ppe_violation":              HazardTypeEnum.PPE,
    "ppe_missing":                HazardTypeEnum.PPE,
    "ergonomic_risk":             HazardTypeEnum.Ergonomics,
    "intrusion":                  HazardTypeEnum.Intrusion,
}


# ── Result type ───────────────────────────────────────────────────────

@dataclass
class IngestResult:
    status: str                              # "accepted" | "duplicate" | "ergonomic_only"
    incident_id: Optional[str] = None
    alert_id: Optional[str] = None
    ergonomic_record_id: Optional[str] = None
    record_only: bool = False
    incident: Optional[Incident] = field(default=None, repr=False)  # for WS broadcast

    def to_response(self) -> dict:
        resp: dict = {"status": self.status}
        if self.incident_id:
            resp["incident_id"] = self.incident_id
        if self.alert_id:
            resp["alert_id"] = self.alert_id
        if self.ergonomic_record_id:
            resp["ergonomic_record_id"] = self.ergonomic_record_id
        if self.record_only:
            resp["record_only"] = True
        return resp


# ── Mapping helpers ───────────────────────────────────────────────────

def _map_severity(raw: str) -> SeverityEnum:
    return _SEVERITY_MAP.get(raw.upper(), SeverityEnum.Medium)


def _map_hazard_type(event_type: str) -> HazardTypeEnum:
    lower = event_type.lower()
    if lower.startswith("zone_"):
        return HazardTypeEnum.Intrusion
    for key, val in _HAZARD_TYPE_MAP.items():
        if key in lower:
            return val
    if "fall" in lower:
        return HazardTypeEnum.Fall
    if "overspeed" in lower:
        return HazardTypeEnum.Overspeed
    if "forklift" in lower or "proximity" in lower:
        return HazardTypeEnum.Proximity
    if "ppe" in lower or "helmet" in lower or "vest" in lower:
        return HazardTypeEnum.PPE
    if "ergo" in lower or "posture" in lower:
        return HazardTypeEnum.Ergonomics
    return HazardTypeEnum.Intrusion


def _normalize_risk_level(raw: Optional[str], severity: SeverityEnum) -> RiskLevelEnum:
    if raw:
        lowered = raw.strip().lower()
        if "critical" in lowered or "very high" in lowered:
            return RiskLevelEnum.Critical
        if "high" in lowered:
            return RiskLevelEnum.High
        if "medium" in lowered:
            return RiskLevelEnum.Medium
        if any(t in lowered for t in ("low", "acceptable", "negligible")):
            return RiskLevelEnum.Low
    if severity == SeverityEnum.Critical:
        return RiskLevelEnum.Critical
    if severity == SeverityEnum.High:
        return RiskLevelEnum.High
    if severity == SeverityEnum.Low:
        return RiskLevelEnum.Low
    return RiskLevelEnum.Medium


# ── Extraction helpers ────────────────────────────────────────────────

def _extract_zone(payload: HazardEventPayload) -> str:
    if isinstance(payload.metadata, dict):
        for key in ("zone", "location", "camera_zone"):
            if payload.metadata.get(key):
                return str(payload.metadata[key])
    return f"Camera {payload.camera_id}"


def _extract_metadata_value(payload: HazardEventPayload, key: str) -> Optional[str]:
    value = getattr(payload, key, None)
    if value:
        return str(value)
    if isinstance(payload.metadata, dict):
        meta_value = payload.metadata.get(key)
        if meta_value:
            return str(meta_value)
    return None


def _extract_thumbnail(payload: HazardEventPayload) -> Optional[str]:
    if isinstance(payload.metadata, dict):
        for key in ("snapshot_data_url", "thumbnail", "image", "frame_image"):
            if payload.metadata.get(key):
                return str(payload.metadata[key])
    return _extract_metadata_value(payload, "thumbnail")


def _extract_event_frame(payload: HazardEventPayload) -> Optional[str]:
    if isinstance(payload.metadata, dict):
        for key in ("event_frame_data_url", "event_frame", "exact_event_frame_data_url"):
            if payload.metadata.get(key):
                return str(payload.metadata[key])
    return _extract_metadata_value(payload, "event_frame")


def _extract_video_evidence(payload: HazardEventPayload) -> Optional[str]:
    if isinstance(payload.metadata, dict):
        for key in ("video_evidence_data_url", "video_evidence", "video"):
            if payload.metadata.get(key):
                return str(payload.metadata[key])
    return _extract_metadata_value(payload, "video_evidence")


def _extract_confidence(payload: HazardEventPayload) -> Optional[float]:
    if not isinstance(payload.metadata, dict):
        return None
    for key in ("confidence", "score", "alert_confidence"):
        value = payload.metadata.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _is_composite_payload(payload: HazardEventPayload) -> bool:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    return bool(metadata.get("composite") or metadata.get("correlation_id"))


def _composite_metadata(payload: HazardEventPayload) -> dict:
    return payload.metadata if isinstance(payload.metadata, dict) else {}


def _composite_incident_id(correlation_id: object) -> str:
    digest = hashlib.sha1(str(correlation_id).encode("utf-8")).hexdigest()[:16]
    return f"INC-COMP-{digest}"


def _proximity_incident_id(operational_case_id: object) -> str:
    digest = hashlib.sha1(str(operational_case_id).encode("utf-8")).hexdigest()[:16]
    return f"INC-PROX-{digest}"


def _parent_proximity_incident_id(payload: HazardEventPayload) -> Optional[str]:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    parent = metadata.get("parent_operational_case_id")
    if not parent:
        return None
    return _proximity_incident_id(parent)


def _is_operational_proximity_payload(payload: HazardEventPayload) -> bool:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    return bool(metadata.get("operational_case_id")) and (
        metadata.get("case_type") == "forklift_proximity"
        or str(payload.event_type or "").lower() == "forklift_proximity"
    )


def _proximity_metadata(payload: HazardEventPayload) -> dict:
    return payload.metadata if isinstance(payload.metadata, dict) else {}


def _component_hazards(payload: HazardEventPayload) -> list[dict]:
    metadata = _composite_metadata(payload)
    components = metadata.get("component_hazards")
    if isinstance(components, list):
        return [item for item in components if isinstance(item, dict)]
    source_events = metadata.get("source_events")
    if not isinstance(source_events, list):
        return []
    return [
        {
            "label": str(source.get("event_type", "Hazard")).replace("_", " ").title(),
            "event_type": source.get("event_type"),
            "severity": source.get("severity"),
            "track_id": source.get("track_id"),
            "worker_track_id": source.get("worker_track_id"),
            "forklift_track_id": source.get("forklift_track_id"),
            "frame_number": source.get("frame_number"),
            "timestamp": source.get("timestamp"),
            "bbox": source.get("bbox"),
        }
        for source in source_events
        if isinstance(source, dict)
    ]


def _record_composite_timeline(
    db: Session,
    *,
    incident_id: str,
    payload: HazardEventPayload,
    alert_id: str | None,
) -> None:
    if not _is_composite_payload(payload):
        return
    metadata = _composite_metadata(payload)
    components = _component_hazards(payload)
    correlation_id = metadata.get("correlation_id")
    IncidentTimelineService.record_event(
        db,
        incident_id=incident_id,
        action="composite_created",
        previous_status=None,
        new_status=IncidentStatusEnum.Active.value,
        actor_name="Edge AI",
        note="Composite hazard accepted as the primary operational incident",
        metadata={
            "correlation_id": correlation_id,
            "source_event_types": metadata.get("source_event_types"),
            "component_hazards": components,
            "alert_id": alert_id,
        },
    )
    for component in components:
        label = component.get("label") or str(component.get("event_type", "Hazard")).replace("_", " ").title()
        IncidentTimelineService.record_event(
            db,
            incident_id=incident_id,
            action="source_hazard_attached",
            previous_status=None,
            new_status=IncidentStatusEnum.Active.value,
            actor_name="Edge AI",
            note=f"Contributing hazard attached: {label}",
            metadata={
                "correlation_id": correlation_id,
                "component_hazard": component,
                "alert_id": alert_id,
            },
        )


def _source_incident_ids(payload: HazardEventPayload) -> list[str]:
    metadata = _composite_metadata(payload)
    source_events = metadata.get("source_events")
    if not isinstance(source_events, list):
        return []
    ids: list[str] = []
    for source in source_events:
        if not isinstance(source, dict):
            continue
        try:
            ts = int(float(source.get("timestamp")))
        except (TypeError, ValueError):
            continue
        frame_number = source.get("frame_number") or 0
        track_id = source.get("track_id")
        track_part = f"T{track_id}" if track_id is not None else "TNA"
        ids.append(f"INC-{ts}-{frame_number}-{track_part}")
    return list(dict.fromkeys(ids))


def _merge_existing_source_incidents(
    db: Session,
    *,
    composite_incident_id: str,
    payload: HazardEventPayload,
) -> list[str]:
    if not _is_composite_payload(payload):
        return []
    merged: list[str] = []
    for source_incident_id in _source_incident_ids(payload):
        if source_incident_id == composite_incident_id:
            continue
        incident = db.query(Incident).filter(Incident.id == source_incident_id).first()
        if incident is None:
            continue
        source_alerts = db.query(Alert).filter(Alert.incident_id == source_incident_id).all()
        for alert in source_alerts:
            db.query(AlertEvent).filter(AlertEvent.alert_id == alert.id).delete(synchronize_session=False)
            db.delete(alert)
        db.query(IncidentEvent).filter(IncidentEvent.incident_id == source_incident_id).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.message.like(f"{source_incident_id}:%")).delete(synchronize_session=False)
        db.delete(incident)
        merged.append(source_incident_id)
    return merged


def _record_source_merge_timeline(
    db: Session,
    *,
    incident_id: str,
    merged_source_incident_ids: list[str],
    payload: HazardEventPayload,
    alert_id: str | None,
) -> None:
    if not merged_source_incident_ids:
        return
    metadata = _composite_metadata(payload)
    IncidentTimelineService.record_event(
        db,
        incident_id=incident_id,
        action="source_incidents_merged",
        previous_status=None,
        new_status=IncidentStatusEnum.Active.value,
        actor_name="Edge AI",
        note="Source hazard incidents merged into the composite incident",
        metadata={
            "correlation_id": metadata.get("correlation_id"),
            "merged_source_incident_ids": merged_source_incident_ids,
            "source_event_types": metadata.get("source_event_types"),
            "alert_id": alert_id,
        },
    )


def _extract_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


# ── Camera / location resolution ─────────────────────────────────────

def _camera_id_candidates(camera_id: Optional[str]) -> list[str]:
    if not camera_id:
        return []
    raw = str(camera_id).strip()
    candidates = [raw]
    lowered = raw.lower()
    if lowered.startswith("cam_"):
        suffix = lowered.removeprefix("cam_").replace("_", "-")
        candidates.append(f"CAM-{suffix}")
        try:
            candidates.append(f"CAM-{int(suffix):02d}")
        except ValueError:
            pass
    if lowered.startswith("cam-"):
        suffix = lowered.removeprefix("cam-")
        candidates.append(f"CAM-{suffix}")
        try:
            candidates.append(f"CAM-{int(suffix):02d}")
        except ValueError:
            pass
    candidates.append(raw.upper())
    return list(dict.fromkeys(candidates))


def _resolve_camera(db: Session, camera_id: Optional[str]) -> Camera | None:
    for candidate in _camera_id_candidates(camera_id):
        camera = db.query(Camera).filter(Camera.id == candidate).first()
        if camera:
            return camera
    return None


def _resolve_location(db: Session, payload: HazardEventPayload) -> dict:
    camera = _resolve_camera(db, payload.camera_id)
    area = db.query(Area).filter(Area.id == camera.area_id).first() if camera and camera.area_id else None
    zone = db.query(Zone).filter(Zone.id == camera.zone_id).first() if camera and camera.zone_id else None

    fallback_zone = _extract_zone(payload)
    zone_name = zone.name if zone else (camera.zone if camera and camera.zone else fallback_zone)
    area_name = area.name if area else None
    return {
        "camera_id": camera.id if camera else (payload.camera_id or "unknown"),
        "camera_name": camera.name if camera else None,
        "area_id": area.id if area else (camera.area_id if camera else None),
        "area_name": area_name,
        "zone_id": zone.id if zone else (camera.zone_id if camera else None),
        "zone_name": zone_name,
        "zone_display": f"{area_name} / {zone_name}" if area_name and zone_name else zone_name,
        "location_description": camera.location_description if camera else None,
    }


def _resolve_camera_name(db: Session, camera_id: Optional[str], fallback: Optional[str]) -> Optional[str]:
    if fallback:
        return fallback
    if not camera_id:
        return None
    camera = _resolve_camera(db, camera_id)
    return camera.name if camera and camera.name else camera_id


def _normalize_camera_zone_value(camera_id: Optional[str], zone_display: Optional[str]) -> str:
    if zone_display:
        return zone_display
    if camera_id:
        return f"Camera {camera_id}"
    return "Unknown Zone"


def _resolve_camera_safety_zone(db: Session, payload: HazardEventPayload) -> CameraSafetyZone | None:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    zone_id = metadata.get("safety_zone_id") or metadata.get("camera_safety_zone_id")
    if not zone_id:
        return None
    return db.query(CameraSafetyZone).filter(
        CameraSafetyZone.id == str(zone_id),
        CameraSafetyZone.deleted_at.is_(None),
    ).first()


# ── Ergonomic helpers ─────────────────────────────────────────────────

def _is_ergonomic_event(event_type: str, payload: HazardEventPayload) -> bool:
    if any(t in event_type.lower() for t in ("ergo", "ergonomic", "posture", "rula", "reba")):
        return True
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    return any(metadata.get(k) is not None for k in ("rula_score", "reba_score", "rula_risk", "reba_risk"))


def _is_record_only_ergonomic(payload: HazardEventPayload, event_type: str) -> bool:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    return bool(metadata.get("record_only")) and _is_ergonomic_event(event_type, payload)


def _build_ergonomic_record(
    incident_id: str,
    payload: HazardEventPayload,
    *,
    event_type: str,
    severity: SeverityEnum,
    camera_id: str,
    zone: str,
    description: str,
    ts: float,
) -> ErgonomicRecord | None:
    if not _is_ergonomic_event(event_type, payload):
        return None
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    risk_hint = metadata.get("reba_risk") or metadata.get("rula_risk") or metadata.get("risk_level")
    return ErgonomicRecord(
        id=f"ERGO-{incident_id}",
        camera_id=camera_id,
        zone=zone,
        track_id=_extract_int(_extract_metadata_value(payload, "track_id")),
        risk_level=_normalize_risk_level(str(risk_hint) if risk_hint is not None else None, severity),
        rula_score=metadata.get("rula_score"),
        reba_score=metadata.get("reba_score"),
        description=description,
        recorded_at=datetime.fromtimestamp(ts, tz=timezone.utc),
    )


# ── Payload normalisation ─────────────────────────────────────────────

@dataclass
class _NormalisedEvent:
    ts: float
    incident_id: str
    severity: SeverityEnum
    zone: str
    classification: str
    description: str
    camera_id: str
    event_type: str


def _normalise_payload(payload: HazardEventPayload) -> _NormalisedEvent:
    """Detect format and return a unified event representation."""
    is_converted = bool(payload.classification or payload.zone) and not payload.event_type
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    correlation_id = metadata.get("correlation_id")
    operational_case_id = metadata.get("operational_case_id")

    if is_converted:
        ts = time.time()
        incident_id = payload.id or f"INC-AI-{int(ts)}"
        severity_raw = str(payload.severity or "Medium")
        sev_map = {
            "critical": SeverityEnum.Critical,
            "high": SeverityEnum.High,
            "medium": SeverityEnum.Medium,
            "low": SeverityEnum.Low,
        }
        severity = sev_map.get(severity_raw.lower(), SeverityEnum.Medium)
        zone = payload.zone or "Unknown Zone"
        classification = payload.classification or "Hazard"
        description = payload.root_cause or f"Auto-detected: {classification}"
        camera_id = payload.camera_id or "unknown"
        event_type = classification.lower().replace(" ", "_")
        if isinstance(payload.metadata, dict) and payload.metadata.get("event_type"):
            event_type = str(payload.metadata["event_type"]).lower()
        if _is_operational_proximity_payload(payload):
            event_type = "forklift_proximity"
        if event_type == "forklift_overspeed":
            classification = "Forklift Overspeed"
    else:
        ts = payload.timestamp or time.time()
        track_part = f"T{payload.track_id}" if payload.track_id is not None else "TNA"
        incident_id = f"INC-{int(ts)}-{payload.frame_number or 0}-{track_part}"
        severity = _map_severity(payload.severity or "MEDIUM")
        zone = _extract_zone(payload)
        classification = str(payload.event_type or "Hazard").replace("_", " ").title()
        description = payload.description or f"Auto-detected: {classification}"
        camera_id = payload.camera_id or "unknown"
        event_type = (payload.event_type or "hazard").lower()
        if event_type == "forklift_overspeed":
            classification = "Forklift Overspeed"

    if correlation_id:
        incident_id = _composite_incident_id(correlation_id)
    elif operational_case_id and _is_operational_proximity_payload(payload):
        incident_id = _proximity_incident_id(operational_case_id)

    return _NormalisedEvent(
        ts=ts,
        incident_id=incident_id,
        severity=severity,
        zone=zone,
        classification=classification,
        description=description,
        camera_id=camera_id,
        event_type=event_type,
    )


def _severity_rank(severity: SeverityEnum) -> int:
    return {
        SeverityEnum.Low: 1,
        SeverityEnum.Medium: 2,
        SeverityEnum.High: 3,
        SeverityEnum.Critical: 4,
    }.get(severity, 0)


def _proximity_timeline_action(lifecycle: str, severity_increased: bool, severity_decreased: bool) -> str:
    if lifecycle == "resolved":
        return "resolved"
    if lifecycle == "reopened":
        return "reopened"
    if lifecycle == "escalated" or severity_increased:
        return "risk_escalated"
    if lifecycle == "deescalated" or severity_decreased:
        return "risk_deescalated"
    return "active_update"


def _update_operational_proximity_incident(
    db: Session,
    *,
    incident: Incident,
    payload: HazardEventPayload,
    ev: _NormalisedEvent,
    location: dict,
    camera_id: str,
    worker_id: str,
    worker_gpu_id: Optional[str],
) -> IngestResult:
    metadata = _proximity_metadata(payload)
    lifecycle = str(metadata.get("event_lifecycle") or metadata.get("lifecycle") or "active_update")
    occurred_at = datetime.fromtimestamp(ev.ts, tz=timezone.utc)
    previous_status = incident.status.value if hasattr(incident.status, "value") else str(incident.status)
    previous_severity = incident.severity
    previous_rank = _severity_rank(previous_severity)
    next_rank = _severity_rank(ev.severity)
    severity_increased = next_rank > previous_rank
    severity_decreased = next_rank < previous_rank
    action = _proximity_timeline_action(lifecycle, severity_increased, severity_decreased)

    incident.zone = _normalize_camera_zone_value(camera_id, location["zone_display"] or ev.zone)
    incident.classification = ev.classification
    incident.root_cause = ev.description
    incident.camera_id = camera_id
    incident.camera_name = location["camera_name"] or incident.camera_name
    incident.worker_id = worker_id
    incident.worker_gpu_id = worker_gpu_id
    incident.severity = ev.severity

    if lifecycle == "resolved":
        incident.status = IncidentStatusEnum.Resolved
        incident.resolved_at = occurred_at
        incident.resolved_by = "Edge AI"
        start = incident.started_at or incident.validated_at or incident.created_at
        if start is not None:
            incident.duration_seconds = max(0, int((occurred_at - _aware(start)).total_seconds()))
    elif lifecycle == "reopened":
        incident.status = IncidentStatusEnum.Active
        incident.resolved_at = None
        incident.resolved_by = None
        incident.duration_seconds = None
    elif incident.status in {
        IncidentStatusEnum.Resolved,
        IncidentStatusEnum.False_Positive,
        IncidentStatusEnum.Archived,
    }:
        incident.status = IncidentStatusEnum.Active
        incident.resolved_at = None
        incident.resolved_by = None
    else:
        incident.status = IncidentStatusEnum.Active

    if severity_increased:
        incident.escalation_count = (incident.escalation_count or 0) + 1

    alert = db.query(Alert).filter(Alert.incident_id == incident.id).order_by(Alert.created_at.asc()).first()
    if alert is not None:
        alert.severity = incident.severity
        alert.description = ev.description
        alert.zone = incident.zone
        alert.status = StatusEnum.Resolved if lifecycle == "resolved" else StatusEnum.Active
        if lifecycle == "resolved":
            alert.resolved_at = occurred_at
            alert.resolved_by = "Edge AI"
        elif lifecycle == "reopened":
            alert.resolved_at = None
            alert.resolved_by = None

    IncidentTimelineService.record_event(
        db,
        incident_id=incident.id,
        action=action,
        previous_status=previous_status,
        new_status=incident.status.value,
        actor_name="Edge AI",
        note=f"Forklift proximity lifecycle update: {lifecycle}",
        metadata={
            "event_type": ev.event_type,
            "operational_case_id": metadata.get("operational_case_id"),
            "event_lifecycle": lifecycle,
            "risk_level": metadata.get("risk_level"),
            "risk_score": metadata.get("risk_score"),
            "proximity_alert_stage": metadata.get("proximity_alert_stage"),
            "previous_severity": previous_severity.value if hasattr(previous_severity, "value") else str(previous_severity),
            "severity": ev.severity.value,
            "alert_id": alert.id if alert else None,
            "frame_number": payload.frame_number,
            "track_id": payload.track_id,
        },
    )
    if alert is not None:
        AlertService.record_event(
            db,
            alert_id=alert.id,
            action=action,
            previous_status=None,
            new_status=alert.status.value if hasattr(alert.status, "value") else str(alert.status),
            actor_name="Edge AI",
            note=f"Forklift proximity lifecycle update: {lifecycle}",
            metadata={
                "incident_id": incident.id,
                "operational_case_id": metadata.get("operational_case_id"),
                "event_type": ev.event_type,
                "risk_level": metadata.get("risk_level"),
                "risk_score": metadata.get("risk_score"),
            },
        )

    if ev.severity == SeverityEnum.Critical and previous_severity != SeverityEnum.Critical:
        NotificationDispatchService.record_incident_notification(
            db,
            incident=incident,
            action="incident_escalated",
            message=f"{incident.id}: forklift proximity escalated to Critical",
            idempotency_key=f"{metadata.get('operational_case_id')}:critical_escalation",
        )

    db.commit()
    db.refresh(incident)
    return IngestResult(
        status="updated",
        incident_id=incident.id,
        alert_id=alert.id if alert else None,
        incident=incident,
    )


def _attach_composite_to_parent_incident(
    db: Session,
    *,
    incident: Incident,
    payload: HazardEventPayload,
    ev: _NormalisedEvent,
) -> IngestResult:
    metadata = _composite_metadata(payload)
    components = _component_hazards(payload)
    previous_status = incident.status.value if hasattr(incident.status, "value") else str(incident.status)
    previous_severity = incident.severity
    if _severity_rank(ev.severity) > _severity_rank(incident.severity):
        incident.severity = ev.severity
        incident.escalation_count = (incident.escalation_count or 0) + 1
    incident.classification = ev.classification
    incident.root_cause = ev.description
    incident.status = IncidentStatusEnum.Active
    incident.resolved_at = None
    incident.resolved_by = None

    alert = db.query(Alert).filter(Alert.incident_id == incident.id).order_by(Alert.created_at.asc()).first()
    if alert is not None:
        alert.severity = incident.severity
        alert.description = ev.description
        alert.status = StatusEnum.Active
        alert.resolved_at = None
        alert.resolved_by = None

    IncidentTimelineService.record_event(
        db,
        incident_id=incident.id,
        action="composite_attached",
        previous_status=previous_status,
        new_status=incident.status.value,
        actor_name="Edge AI",
        note="Composite PPE + forklift risk attached to active proximity case",
        metadata={
            "correlation_id": metadata.get("correlation_id"),
            "parent_operational_case_id": metadata.get("parent_operational_case_id"),
            "source_event_types": metadata.get("source_event_types"),
            "component_hazards": components,
            "previous_severity": previous_severity.value if hasattr(previous_severity, "value") else str(previous_severity),
            "severity": ev.severity.value,
            "alert_id": alert.id if alert else None,
        },
    )
    for component in components:
        label = component.get("label") or str(component.get("event_type", "Hazard")).replace("_", " ").title()
        IncidentTimelineService.record_event(
            db,
            incident_id=incident.id,
            action="source_hazard_attached",
            previous_status=None,
            new_status=incident.status.value,
            actor_name="Edge AI",
            note=f"Contributing hazard attached: {label}",
            metadata={
                "correlation_id": metadata.get("correlation_id"),
                "parent_operational_case_id": metadata.get("parent_operational_case_id"),
                "component_hazard": component,
                "alert_id": alert.id if alert else None,
            },
        )

    if ev.severity == SeverityEnum.Critical and previous_severity != SeverityEnum.Critical:
        NotificationDispatchService.record_incident_notification(
            db,
            incident=incident,
            action="incident_escalated",
            message=f"{incident.id}: composite PPE + forklift risk escalated to Critical",
            idempotency_key=f"{metadata.get('parent_operational_case_id')}:composite_critical",
        )

    db.commit()
    db.refresh(incident)
    return IngestResult(
        status="updated",
        incident_id=incident.id,
        alert_id=alert.id if alert else None,
        incident=incident,
    )


# ── Public service API ────────────────────────────────────────────────

class IngestService:

    @staticmethod
    def process(db: Session, payload: HazardEventPayload) -> IngestResult:
        ev = _normalise_payload(payload)
        location = _resolve_location(db, payload)
        payload_metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        camera_safety_zone = _resolve_camera_safety_zone(db, payload)

        camera_id = location["camera_id"] or ev.camera_id
        zone = _normalize_camera_zone_value(
            camera_id,
            camera_safety_zone.name if camera_safety_zone is not None else (location["zone_display"] or ev.zone),
        )
        camera_name = (
            _extract_metadata_value(payload, "camera_name")
            or location["camera_name"]
            or _resolve_camera_name(db, camera_id, None)
        )
        track_id = _extract_metadata_value(payload, "track_id")
        raw_worker = _extract_metadata_value(payload, "worker_id")
        if track_id is not None and str(track_id).strip():
            worker_id = f"Worker D{track_id}"
        elif raw_worker and not any(c in raw_worker for c in ("-", "_")) and len(raw_worker) < 6:
            worker_id = f"Worker D{raw_worker}"
        else:
            worker_id = "Worker D1"
        worker_gpu_id = _extract_metadata_value(payload, "worker_gpu_id")

        # ── Ergonomic-only path ─────────────────────────────────────
        if _is_record_only_ergonomic(payload, ev.event_type):
            record_id = (
                payload.id
                or f"ERGO-{camera_id}-{int(ev.ts)}-{payload.frame_number or 0}-{payload.track_id or 'TNA'}"
            )
            ergo = _build_ergonomic_record(
                record_id, payload,
                event_type=ev.event_type, severity=ev.severity,
                camera_id=camera_id, zone=zone, description=ev.description, ts=ev.ts,
            )
            if ergo is not None:
                ergo.id = record_id if str(record_id).startswith("ERGO-") else f"ERGO-{record_id}"
                if db.query(ErgonomicRecord).filter(ErgonomicRecord.id == ergo.id).first() is None:
                    db.add(ergo)
                    db.commit()
                return IngestResult(status="accepted", ergonomic_record_id=ergo.id, record_only=True)

        parent_proximity_incident_id = _parent_proximity_incident_id(payload)
        if parent_proximity_incident_id:
            parent_incident = db.query(Incident).filter(Incident.id == parent_proximity_incident_id).first()
            if parent_incident is not None:
                return _attach_composite_to_parent_incident(
                    db,
                    incident=parent_incident,
                    payload=payload,
                    ev=ev,
                )

        # ── Duplicate check ─────────────────────────────────────────
        merged_source_incident_ids = _merge_existing_source_incidents(
            db,
            composite_incident_id=ev.incident_id,
            payload=payload,
        )
        existing_incident = db.query(Incident).filter(Incident.id == ev.incident_id).first()
        if existing_incident:
            if _is_operational_proximity_payload(payload):
                return _update_operational_proximity_incident(
                    db,
                    incident=existing_incident,
                    payload=payload,
                    ev=ev,
                    location=location,
                    camera_id=camera_id,
                    worker_id=worker_id,
                    worker_gpu_id=worker_gpu_id,
                )
            _record_source_merge_timeline(
                db,
                incident_id=ev.incident_id,
                merged_source_incident_ids=merged_source_incident_ids,
                payload=payload,
                alert_id=None,
            )
            if merged_source_incident_ids:
                db.commit()
            logger.debug("Duplicate incident skipped: %s", ev.incident_id)
            return IngestResult(status="duplicate", incident_id=ev.incident_id)

        # ── Incident ────────────────────────────────────────────────
        occurred_at = datetime.fromtimestamp(ev.ts, tz=timezone.utc)
        incident = Incident(
            id=ev.incident_id,
            zone=zone,
            classification=ev.classification,
            severity=ev.severity,
            camera_id=camera_id,
            camera_name=camera_name,
            worker_id=worker_id,
            worker_gpu_id=worker_gpu_id,
            status=IncidentStatusEnum.Active,
            started_at=occurred_at,
            validated_at=occurred_at,
            escalation_count=1 if payload_metadata.get("escalated") else 0,
            root_cause=ev.description,
            corrective_action=payload.corrective_action or "Review detection and acknowledge",
            created_at=occurred_at,
        )
        db.add(incident)
        db.flush()

        event_metadata = payload_metadata
        event_frame_number = _extract_int(
            _extract_metadata_value(payload, "event_frame_number")
            or _extract_metadata_value(payload, "frame_number")
        )
        event_frame_width = _extract_int(
            _extract_metadata_value(payload, "event_frame_width")
            or _extract_metadata_value(payload, "snapshot_width")
        )
        event_frame_height = _extract_int(
            _extract_metadata_value(payload, "event_frame_height")
            or _extract_metadata_value(payload, "snapshot_height")
        )
        event_track_id = _extract_int(
            _extract_metadata_value(payload, "track_id")
            or _extract_metadata_value(payload, "event_track_id")
        )
        evidence_kind = (
            _extract_metadata_value(payload, "evidence_kind")
            or ("video_clip" if _extract_video_evidence(payload) else None)
        )
        event_frame_path = EvidenceService.save_data_url(
            camera_id=camera_id,
            incident_id=ev.incident_id,
            data_url=_extract_event_frame(payload),
            kind="event-frame",
            event_metadata=event_metadata,
        )
        snapshot_path = EvidenceService.save_data_url(
            camera_id=camera_id,
            incident_id=ev.incident_id,
            data_url=_extract_thumbnail(payload),
            kind="snapshot",
            event_metadata=event_metadata,
        )
        video_evidence = EvidenceService.save_data_url(
            camera_id=camera_id,
            incident_id=ev.incident_id,
            data_url=_extract_video_evidence(payload),
            kind="clip",
            event_metadata=event_metadata,
        )
        NotificationDispatchService.record_incident_notification(
            db,
            incident=incident,
            action="incident_created",
            message=f"{incident.id}: {incident.classification} opened from edge detection",
            idempotency_key=(
                f"{event_metadata.get('operational_case_id')}:incident_created"
                if _is_operational_proximity_payload(payload) and event_metadata.get("operational_case_id")
                else None
            ),
        )

        # ── Alert signal ────────────────────────────────────────────
        # Incidents own lifecycle. Alerts are retained as detection signals and
        # evidence attachments for every accepted edge event, including CRITICAL.
        alert_id = f"ALT-AI-{int(ev.ts)}-{uuid.uuid4().hex[:6]}"
        alert = Alert(
            id=alert_id,
            incident_id=incident.id,
            type=_map_hazard_type(ev.event_type),
            severity=ev.severity,
            zone=zone,
            area_id=location["area_id"],
            area_name=location["area_name"],
            zone_id=camera_safety_zone.id if camera_safety_zone is not None else location["zone_id"],
            zone_name=camera_safety_zone.name if camera_safety_zone is not None else location["zone_name"],
            location_description=location["location_description"],
            camera=camera_id,
            camera_id=camera_id,
            camera_name=camera_name,
            worker_id=worker_id,
            worker_gpu_id=worker_gpu_id,
            occurred_at=datetime.fromtimestamp(ev.ts, tz=timezone.utc),
            status=StatusEnum.New,
            description=ev.description,
            thumbnail=event_frame_path or snapshot_path or _extract_thumbnail(payload),
            event_frame=event_frame_path or snapshot_path or _extract_event_frame(payload),
            video_evidence=video_evidence,
            track_id=event_track_id,
            frame_number=event_frame_number,
            frame_width=event_frame_width,
            frame_height=event_frame_height,
            evidence_kind=evidence_kind,
            confidence=_extract_confidence(payload),
        )
        db.add(alert)
        db.flush()
        IncidentTimelineService.record_event(
            db,
            incident_id=incident.id,
            action="created" if _is_operational_proximity_payload(payload) else "validated",
            previous_status=None,
            new_status=IncidentStatusEnum.Active.value,
            actor_name="Edge AI",
            note=(
                "Forklift proximity operational case created"
                if _is_operational_proximity_payload(payload)
                else "Hazard validated by edge aggregation and opened as an active incident"
            ),
            metadata={
                "event_type": ev.event_type,
                "alert_id": alert.id,
                "camera_id": camera_id,
                "worker_id": worker_id,
                "track_id": event_track_id,
                "frame_number": event_frame_number,
                "event_frame": event_frame_path,
                "snapshot_path": snapshot_path,
                "video_evidence": video_evidence,
                "correlation_id": event_metadata.get("correlation_id"),
                "operational_case_id": event_metadata.get("operational_case_id"),
                "event_lifecycle": event_metadata.get("event_lifecycle"),
                "risk_level": event_metadata.get("risk_level"),
                "risk_score": event_metadata.get("risk_score"),
                "proximity_alert_stage": event_metadata.get("proximity_alert_stage"),
                "safety_zone_id": event_metadata.get("safety_zone_id"),
                "safety_zone_name": event_metadata.get("safety_zone_name"),
                "zone_event_type": event_metadata.get("zone_event_type"),
                "component_hazards": event_metadata.get("component_hazards"),
                "source_events": event_metadata.get("source_events"),
            },
        )
        _record_composite_timeline(
            db,
            incident_id=incident.id,
            payload=payload,
            alert_id=alert.id,
        )
        _record_source_merge_timeline(
            db,
            incident_id=incident.id,
            merged_source_incident_ids=merged_source_incident_ids,
            payload=payload,
            alert_id=alert.id,
        )
        AlertService.record_event(
            db,
            alert_id=alert.id,
            action="created",
            previous_status=None,
            new_status=StatusEnum.New.value,
            actor_name="Edge AI",
            note="Alert signal created from edge hazard event",
            metadata={
                "event_type": ev.event_type,
                "incident_id": ev.incident_id,
                "camera_id": camera_id,
                "worker_id": worker_id,
                "track_id": event_track_id,
                "frame_number": event_frame_number,
                "event_frame": event_frame_path,
            },
        )

        if camera_safety_zone is not None:
            SafetyZoneService.record_event(
                db,
                zone_id=camera_safety_zone.id,
                camera_id=camera_id,
                event_type=str(event_metadata.get("zone_event_type") or ev.event_type),
                object_class=str(event_metadata.get("object_class") or event_metadata.get("detected_class") or "unknown"),
                track_id=event_track_id,
                stable_object_key=str(event_metadata.get("stable_object_key") or event_track_id or "unknown"),
                severity=ev.severity.value,
                occurred_at=occurred_at,
                duration_inside_sec=event_metadata.get("duration_inside_sec"),
                occupancy_count=event_metadata.get("occupancy_count"),
                frame_number=event_frame_number,
                bbox=payload.bbox or event_metadata.get("bbox"),
                anchor_point=event_metadata.get("anchor_point"),
                metadata=event_metadata,
                alert_id=alert.id,
            )

        # ── Ergonomic record (non-exclusive) ────────────────────────
        ergo = _build_ergonomic_record(
            ev.incident_id, payload,
            event_type=ev.event_type, severity=ev.severity,
            camera_id=camera_id, zone=zone, description=ev.description, ts=ev.ts,
        )
        if ergo is not None:
            if db.query(ErgonomicRecord).filter(ErgonomicRecord.id == ergo.id).first() is None:
                db.add(ergo)

        db.commit()
        db.refresh(incident)

        logger.info(
            "Ingest accepted: incident=%s type=%s severity=%s camera=%s camera_name=%s worker_id=%s",
            ev.incident_id, ev.classification, ev.severity.value, camera_id, camera_name, worker_id,
        )

        return IngestResult(
            status="accepted",
            incident_id=ev.incident_id,
            alert_id=alert.id if alert else None,
            ergonomic_record_id=ergo.id if ergo else None,
            incident=incident,
        )
