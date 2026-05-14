"""Internal ingest endpoint — receives raw hazard events from the edge AI pipeline.

This endpoint is intentionally unauthenticated: it is only reachable from
within the Docker internal network (service-to-service). The edge AI subprocess
POSTs HazardEvent payloads here, which are converted into Incident + Alert DB
rows and broadcast to the dashboard via WebSocket.

URL: POST /api/ingest/incident
"""
from __future__ import annotations


import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...api.websocket.ws_handler import incident_ws_manager, serialize_incident
from ...models import Alert, Camera, Incident
from ...models.models import HazardTypeEnum, SeverityEnum, StatusEnum

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger("visionsafe.ingest")


# ── Request schema ────────────────────────────────────────────────────
# Accepts BOTH raw HazardEvent format (from edge AI subprocess)
# AND the IncidentCreate/converted format (from BackendClient._event_to_payload).

class HazardEventPayload(BaseModel):
    """Flexible schema — handles both raw HazardEvent and pre-converted payloads."""

    # Raw HazardEvent fields
    event_type: Optional[str] = None
    severity: Optional[str] = None      # "HIGH", "MEDIUM", "LOW", "CRITICAL"
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    worker_id: Optional[str] = None
    worker_gpu_id: Optional[str] = None
    timestamp: Optional[float] = None
    frame_number: Optional[int] = None
    track_id: Optional[int] = None
    description: Optional[str] = None
    metadata: Optional[Any] = None
    bbox: Optional[Any] = None

    # Pre-converted IncidentCreate fields (from BackendClient._event_to_payload)
    id: Optional[str] = None
    zone: Optional[str] = None
    classification: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    created_at: Optional[Any] = None


# ── Helpers ─────────────────────────────────────────────────────────

_SEVERITY_MAP: dict[str, SeverityEnum] = {
    "CRITICAL": SeverityEnum.High,
    "HIGH":     SeverityEnum.High,
    "MEDIUM":   SeverityEnum.Medium,
    "LOW":      SeverityEnum.Low,
}

_HAZARD_TYPE_MAP: dict[str, HazardTypeEnum] = {
    "fall_confirmed":               HazardTypeEnum.Fall,
    "fall_candidate":               HazardTypeEnum.Fall,
    "forklift_proximity_danger":    HazardTypeEnum.Proximity,
    "forklift_proximity_warning":   HazardTypeEnum.Proximity,
    "ppe_violation":                HazardTypeEnum.PPE,
    "ppe_missing":                  HazardTypeEnum.PPE,
    "ergonomic_risk":               HazardTypeEnum.Ergonomics,
    "intrusion":                    HazardTypeEnum.Intrusion,
}


def _map_severity(raw: str) -> SeverityEnum:
    return _SEVERITY_MAP.get(raw.upper(), SeverityEnum.Medium)


def _map_hazard_type(event_type: str) -> HazardTypeEnum:
    lower = event_type.lower()
    for key, val in _HAZARD_TYPE_MAP.items():
        if key in lower:
            return val
    if "fall" in lower:
        return HazardTypeEnum.Fall
    if "forklift" in lower or "proximity" in lower:
        return HazardTypeEnum.Proximity
    if "ppe" in lower or "helmet" in lower or "vest" in lower:
        return HazardTypeEnum.PPE
    if "ergo" in lower or "posture" in lower:
        return HazardTypeEnum.Ergonomics
    return HazardTypeEnum.Intrusion


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


def _resolve_camera_name(db: Session, camera_id: Optional[str], fallback: Optional[str]) -> Optional[str]:
    if fallback:
        return fallback
    if not camera_id:
        return None
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if camera and camera.name:
        return camera.name
    return camera_id


# ── Endpoint ─────────────────────────────────────────────────────────

@router.post("/incident", status_code=202)
async def ingest_incident(payload: HazardEventPayload, db: Session = Depends(get_db)):
    """Accept a raw HazardEvent OR pre-converted IncidentCreate from the edge AI pipeline.

    Creates an Incident row. For HIGH/CRITICAL severities, also creates an
    Alert row and broadcasts via WebSocket.

    No authentication required — secured by Docker internal network only.
    """
    # ── Detect payload format ──────────────────────────────────────────
    # BackendClient._event_to_payload sends: {id, zone, classification, severity, root_cause, corrective_action, created_at}
    # Raw HazardEvent has:                   {event_type, severity, camera_id, timestamp, frame_number, ...}
    is_converted = bool(payload.classification or payload.zone) and not payload.event_type

    if is_converted:
        # Pre-converted format — use directly
        ts = time.time()
        incident_id = payload.id or f"INC-AI-{int(ts)}"
        severity_raw = str(payload.severity or "Medium")
        # Severity from _event_to_payload is already "High"/"Medium"/"Low"
        sev_map = {"high": SeverityEnum.High, "medium": SeverityEnum.Medium, "low": SeverityEnum.Low}
        severity = sev_map.get(severity_raw.lower(), SeverityEnum.Medium)
        zone = payload.zone or "Unknown Zone"
        classification = payload.classification or "Hazard"
        description = payload.root_cause or f"Auto-detected: {classification}"
        camera_id = payload.camera_id or "unknown"
        event_type = classification.lower().replace(" ", "_")
    else:
        # Raw HazardEvent format
        ts = payload.timestamp or time.time()
        track_part = f"T{payload.track_id}" if payload.track_id is not None else "TNA"
        frame_part = payload.frame_number or 0
        incident_id = f"INC-{int(ts)}-{frame_part}-{track_part}"
        severity = _map_severity(payload.severity or "MEDIUM")
        zone = _extract_zone(payload)
        classification = str(payload.event_type or "Hazard").replace("_", " ").title()
        description = payload.description or f"Auto-detected: {classification}"
        camera_id = payload.camera_id or "unknown"
        event_type = (payload.event_type or "hazard").lower()

    camera_name = _resolve_camera_name(db, camera_id, _extract_metadata_value(payload, "camera_name"))
    worker_id = _extract_metadata_value(payload, "worker_id")
    worker_gpu_id = _extract_metadata_value(payload, "worker_gpu_id")

    # ── Incident ────────────────────────────────────────────────────
    existing = db.query(Incident).filter(Incident.id == incident_id).first()
    if existing:
        logger.debug("Duplicate incident skipped: %s", incident_id)
        return {"status": "duplicate", "incident_id": incident_id}

    incident = Incident(
        id=incident_id,
        zone=zone,
        classification=classification,
        severity=severity,
        camera_id=camera_id,
        camera_name=camera_name,
        worker_id=worker_id,
        worker_gpu_id=worker_gpu_id,
        root_cause=description,
        corrective_action=payload.corrective_action or "Review detection and acknowledge",
        created_at=datetime.fromtimestamp(ts, tz=timezone.utc),
    )
    db.add(incident)

    # ── Alert (HIGH / MEDIUM only) ─────────────────────────────────
    alert = None
    if severity in (SeverityEnum.High, SeverityEnum.Medium):
        alert_id = f"ALT-AI-{int(ts)}-{uuid.uuid4().hex[:6]}"
        hazard_type = _map_hazard_type(event_type)
        alert = Alert(
            id=alert_id,
            type=hazard_type,
            severity=severity,
            zone=zone,
            camera=camera_id,
            camera_id=camera_id,
            camera_name=camera_name,
            worker_id=worker_id,
            worker_gpu_id=worker_gpu_id,
            occurred_at=datetime.fromtimestamp(ts, tz=timezone.utc),
            status=StatusEnum.New,
            description=description,
            thumbnail=None,
            confidence=None,
        )
        db.add(alert)

    db.commit()
    db.refresh(incident)

    logger.info(
        "Ingest accepted: incident=%s type=%s severity=%s camera=%s camera_name=%s worker_id=%s worker_gpu_id=%s",
        incident_id, classification, severity.value, camera_id, camera_name, worker_id, worker_gpu_id,
    )

    # ── WebSocket broadcast ─────────────────────────────────────────
    await incident_ws_manager.broadcast({
        "type": "incident_created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incident": serialize_incident(incident),
    })

    return {
        "status": "accepted",
        "incident_id": incident_id,
        "alert_id": alert.id if alert else None,
    }
