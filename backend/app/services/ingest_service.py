"""Ingest service — converts raw edge AI hazard events into DB rows.

Called exclusively by the /ingest/incident route. Handles:
  - Payload format detection (raw HazardEvent vs pre-converted)
  - Severity + hazard-type mapping
  - Camera / area / zone resolution
  - Incident, Alert, and ErgonomicRecord persistence
  - Duplicate detection
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    Alert,
    Area,
    Camera,
    ErgonomicRecord,
    HazardTypeEnum,
    Incident,
    RiskLevelEnum,
    SeverityEnum,
    StatusEnum,
    Zone,
)
from ..schemas.ingest import HazardEventPayload
from .alert_service import AlertService

logger = logging.getLogger("visionsafe.ingest")

# ── Lookup maps ───────────────────────────────────────────────────────

_SEVERITY_MAP: dict[str, SeverityEnum] = {
    "CRITICAL": SeverityEnum.High,
    "HIGH":     SeverityEnum.High,
    "MEDIUM":   SeverityEnum.Medium,
    "LOW":      SeverityEnum.Low,
}

_HAZARD_TYPE_MAP: dict[str, HazardTypeEnum] = {
    "fall_confirmed":             HazardTypeEnum.Fall,
    "fall_candidate":             HazardTypeEnum.Fall,
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

    if is_converted:
        ts = time.time()
        incident_id = payload.id or f"INC-AI-{int(ts)}"
        severity_raw = str(payload.severity or "Medium")
        sev_map = {"high": SeverityEnum.High, "medium": SeverityEnum.Medium, "low": SeverityEnum.Low}
        severity = sev_map.get(severity_raw.lower(), SeverityEnum.Medium)
        zone = payload.zone or "Unknown Zone"
        classification = payload.classification or "Hazard"
        description = payload.root_cause or f"Auto-detected: {classification}"
        camera_id = payload.camera_id or "unknown"
        event_type = classification.lower().replace(" ", "_")
        if isinstance(payload.metadata, dict) and payload.metadata.get("event_type"):
            event_type = str(payload.metadata["event_type"]).lower()
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


# ── Public service API ────────────────────────────────────────────────

class IngestService:

    @staticmethod
    def process(db: Session, payload: HazardEventPayload) -> IngestResult:
        ev = _normalise_payload(payload)
        location = _resolve_location(db, payload)

        camera_id = location["camera_id"] or ev.camera_id
        zone = _normalize_camera_zone_value(camera_id, location["zone_display"] or ev.zone)
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

        # ── Duplicate check ─────────────────────────────────────────
        if db.query(Incident).filter(Incident.id == ev.incident_id).first():
            logger.debug("Duplicate incident skipped: %s", ev.incident_id)
            return IngestResult(status="duplicate", incident_id=ev.incident_id)

        # ── Incident ────────────────────────────────────────────────
        incident = Incident(
            id=ev.incident_id,
            zone=zone,
            classification=ev.classification,
            severity=ev.severity,
            camera_id=camera_id,
            camera_name=camera_name,
            worker_id=worker_id,
            worker_gpu_id=worker_gpu_id,
            root_cause=ev.description,
            corrective_action=payload.corrective_action or "Review detection and acknowledge",
            created_at=datetime.fromtimestamp(ev.ts, tz=timezone.utc),
        )
        db.add(incident)

        # ── Alert (HIGH / MEDIUM only) ──────────────────────────────
        alert = None
        if ev.severity in (SeverityEnum.High, SeverityEnum.Medium):
            alert_id = f"ALT-AI-{int(ev.ts)}-{uuid.uuid4().hex[:6]}"
            alert = Alert(
                id=alert_id,
                type=_map_hazard_type(ev.event_type),
                severity=ev.severity,
                zone=zone,
                area_id=location["area_id"],
                area_name=location["area_name"],
                zone_id=location["zone_id"],
                zone_name=location["zone_name"],
                location_description=location["location_description"],
                camera=camera_id,
                camera_id=camera_id,
                camera_name=camera_name,
                worker_id=worker_id,
                worker_gpu_id=worker_gpu_id,
                occurred_at=datetime.fromtimestamp(ev.ts, tz=timezone.utc),
                status=StatusEnum.New,
                description=ev.description,
                thumbnail=_extract_thumbnail(payload),
                confidence=_extract_confidence(payload),
            )
            db.add(alert)
            db.flush()
            AlertService.record_event(
                db,
                alert_id=alert.id,
                action="created",
                previous_status=None,
                new_status=StatusEnum.New.value,
                actor_name="Edge AI",
                note="Alert created from edge hazard event",
                metadata={
                    "event_type": ev.event_type,
                    "incident_id": ev.incident_id,
                    "camera_id": camera_id,
                    "worker_id": worker_id,
                    "frame_number": payload.frame_number,
                },
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
