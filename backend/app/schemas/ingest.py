"""Ingest endpoint schema — accepts raw HazardEvent payloads from the edge AI pipeline."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class HazardEventPayload(BaseModel):
    """Flexible schema — handles both raw HazardEvent and pre-converted payloads.

    Raw HazardEvent (from edge AI subprocess):
        event_type, severity, camera_id, timestamp, frame_number, track_id, description, metadata, bbox

    Pre-converted (from BackendClient._event_to_payload):
        id, zone, classification, severity, root_cause, corrective_action, created_at
    """

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

    # Pre-converted IncidentCreate fields
    id: Optional[str] = None
    zone: Optional[str] = None
    classification: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    created_at: Optional[Any] = None
