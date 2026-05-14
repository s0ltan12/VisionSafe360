"""Incident routes with pagination, rate limiting, and WebSocket broadcast."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...config.settings import settings
from ...api.websocket.ws_handler import incident_ws_manager, serialize_incident
from ...utils.audit_logger import audit_event, ensure_request_id, get_client_ip_from_request
from ...services.monitoring_service import monitoring_service
from ...services.rate_limit_service import rate_limit_service
from ...schemas import IncidentCreate, IncidentOut, IncidentUpdate, PaginatedResponse
from ...services.incident_service import IncidentService
from ...utils.permissions import require_roles
from ...models import User

router = APIRouter(
    prefix="/incidents",
    tags=["incidents"],
    dependencies=[Depends(require_roles("admin", "operator", "viewer"))],
)
logger = logging.getLogger("visionsafe.incidents")


@router.get(
    "",
    response_model=PaginatedResponse[IncidentOut],
    dependencies=[Depends(require_roles("admin", "operator", "viewer"))],
)
def get_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(
        settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
    ),
    db: Session = Depends(get_db),
):
    items, total = IncidentService.list(db, skip=skip, limit=limit)
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit, has_more=(skip + limit) < total)


@router.get("/all", response_model=List[IncidentOut])
def get_all_incidents(db: Session = Depends(get_db)):
    """Legacy endpoint: returns all incidents for current dashboard compatibility."""
    items, _ = IncidentService.list(db, skip=0, limit=10_000)
    return items


@router.post(
    "",
    response_model=IncidentOut,
    status_code=201,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
async def create_incident(
    payload: IncidentCreate,
    request: Request,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
    x_source_id: str | None = Header(default=None),
    x_camera_id: str | None = Header(default=None),
):
    request_id = ensure_request_id(
        getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    )
    ip_address = getattr(request.state, "client_ip", None) or get_client_ip_from_request(request)
    source_id = (x_source_id or x_camera_id or payload.zone or "unknown").strip() or "unknown"

    allowed, retry_after = rate_limit_service.check_and_consume(source_id)
    if not allowed:
        monitoring_service.record_rate_limited(source_id)
        audit_event("create_incident", user_id=current_user.id, ip_address=ip_address,
                    request_id=request_id, outcome="rate_limited", source_id=source_id)
        raise HTTPException(
            status_code=429,
            detail="Incident ingestion rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    existing = IncidentService.get(db, payload.id)
    if existing is not None:
        audit_event("create_incident", user_id=current_user.id, ip_address=ip_address,
                    request_id=request_id, outcome="duplicate", incident_id=payload.id)
        raise HTTPException(status_code=409, detail=f"Incident '{payload.id}' already exists")

    try:
        incident = IncidentService.create(db, payload)
    except IntegrityError as exc:
        db.rollback()
        audit_event("create_incident", user_id=current_user.id, ip_address=ip_address,
                    request_id=request_id, outcome="duplicate", incident_id=payload.id)
        raise HTTPException(status_code=409, detail=f"Incident '{payload.id}' already exists") from exc

    monitoring_service.record_incident(source_id)
    audit_event("create_incident", user_id=current_user.id, ip_address=ip_address,
                request_id=request_id, outcome="success", incident_id=incident.id)

    await incident_ws_manager.broadcast({
        "type": "incident_created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incident": serialize_incident(incident),
    })
    return incident


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: str, payload: IncidentUpdate, db: Session = Depends(get_db)):
    updated = IncidentService.update(db, incident_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: str, db: Session = Depends(get_db)):
    if not IncidentService.delete(db, incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")