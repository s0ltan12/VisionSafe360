"""Best-effort realtime refresh notifications for dashboard pages."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from .event_bus import publish_analytics, publish_ergonomics

logger = logging.getLogger("visionsafe.realtime_events")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish_analytics_change(payload: dict[str, Any]) -> None:
    try:
        publish_analytics({
            "type": "analytics_changed",
            "changed_at": _now(),
            **payload,
        })
    except Exception:
        logger.exception("failed to publish analytics refresh event")


def publish_ergonomics_record_created(record) -> None:
    recorded_at = record.recorded_at.isoformat() if record.recorded_at else None
    changed_at = _now()
    ergonomics_payload = {
        "type": "ergonomic_record_created",
        "domain": "ergonomics",
        "entity_id": record.id,
        "record_id": record.id,
        "camera_id": record.camera_id,
        "zone": record.zone,
        "risk_level": record.risk_level.value if hasattr(record.risk_level, "value") else str(record.risk_level),
        "recorded_at": recorded_at,
        "changed_at": changed_at,
    }
    try:
        publish_ergonomics(ergonomics_payload)
    except Exception:
        logger.exception("failed to publish ergonomics refresh event")

    publish_analytics_change({
        "domain": "ergonomics",
        "entity_id": record.id,
        "changed_at": changed_at,
    })


def publish_alert_change(alert, action: str) -> None:
    publish_analytics_change({
        "domain": "alert",
        "action": action,
        "entity_id": alert.id,
        "severity": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
        "status": alert.status.value if hasattr(alert.status, "value") else str(alert.status),
    })


def publish_alert_deleted(alert_id: str) -> None:
    publish_analytics_change({
        "domain": "alert",
        "action": "alert_deleted",
        "entity_id": alert_id,
    })


def publish_incident_change(incident, action: str) -> None:
    publish_analytics_change({
        "domain": "incident",
        "action": action,
        "entity_id": incident.id,
        "severity": incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
        "status": incident.status.value if hasattr(incident.status, "value") else str(incident.status),
    })


def publish_incident_deleted(incident_id: str) -> None:
    publish_analytics_change({
        "domain": "incident",
        "action": "incident_deleted",
        "entity_id": incident_id,
    })
