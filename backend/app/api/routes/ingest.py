"""Internal ingest endpoint — receives raw hazard events from the edge AI pipeline.

Intentionally unauthenticated: reachable only from within the Docker internal
network (service-to-service). The edge AI process POSTs HazardEvent payloads
here; all business logic lives in IngestService.

URL: POST /api/ingest/incident
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...api.websocket.ws_handler import incident_ws_manager, serialize_incident
from ...schemas.ingest import HazardEventPayload
from ...services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/incident", status_code=202)
async def ingest_incident(payload: HazardEventPayload, db: Session = Depends(get_db)):
    result = IngestService.process(db, payload)

    if result.incident is not None:
        await incident_ws_manager.broadcast({
            "type": "incident_created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident": serialize_incident(result.incident),
        })

    return result.to_response()
