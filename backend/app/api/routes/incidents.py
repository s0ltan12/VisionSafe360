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
from ...schemas import IncidentCreate, IncidentEventOut, IncidentOut, IncidentStatusUpdate, IncidentUpdate, PaginatedResponse
from ...models import IncidentStatusEnum, User
from ...services.incident_command_service import IncidentCommandService
from ...services.incident_service import IncidentService
from ...services.sla_service import SLAService
from ...utils.permissions import require_roles
from ...utils.security import normalize_role

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
    view: str | None = Query(None, pattern="^(active|history)$"),
    db: Session = Depends(get_db),
):
    items, total = IncidentService.list(db, skip=skip, limit=limit, view=view)
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit, has_more=(skip + limit) < total)


@router.get("/all", response_model=List[IncidentOut])
def get_all_incidents(
    view: str | None = Query(None, pattern="^(active|history)$"),
    db: Session = Depends(get_db),
):
    """Legacy endpoint: returns all incidents for current dashboard compatibility."""
    items, _ = IncidentService.list(db, skip=0, limit=10_000, view=view)
    return items


@router.get("/sla/summary")
def get_sla_summary(db: Session = Depends(get_db)):
    return SLAService.get_summary(db)


@router.post("/sla/check")
def check_sla_breaches(
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    del current_user
    return SLAService.check_all(db)


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


@router.post("/{incident_id}/sla/check", response_model=IncidentOut)
def check_incident_sla(
    incident_id: str,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    del current_user
    incident = SLAService.check_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.get("/{incident_id}/events", response_model=List[IncidentEventOut])
def get_incident_events(incident_id: str, db: Session = Depends(get_db)):
    incident = IncidentService.get(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentService.list_events(db, incident_id)


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = IncidentService.get(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    del current_user
    updated = IncidentService.update(db, incident_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/status", response_model=IncidentOut)
def update_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    current = IncidentService.get(db, incident_id)
    if not current:
        raise HTTPException(status_code=404, detail="Incident not found")
    role = normalize_role(current_user.role)
    if payload.status == IncidentStatusEnum.Archived and role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to archive incidents")
    if (
        payload.status == IncidentStatusEnum.Active
        and current.status in {IncidentStatusEnum.Resolved, IncidentStatusEnum.False_Positive, IncidentStatusEnum.Archived}
        and role != "admin"
    ):
        raise HTTPException(status_code=403, detail="Admin role required to reopen incidents")

    updated = IncidentCommandService.transition_status(
        db,
        incident_id,
        payload.status,
        actor=current_user,
        note=payload.note,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/acknowledge", response_model=IncidentOut)
def acknowledge_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    updated = IncidentCommandService.acknowledge(db, incident_id, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/resolve", response_model=IncidentOut)
def resolve_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    updated = IncidentCommandService.resolve(db, incident_id, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/archive", response_model=IncidentOut)
def archive_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    updated = IncidentCommandService.archive(db, incident_id, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/reopen", response_model=IncidentOut)
def reopen_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    updated = IncidentCommandService.reopen(db, incident_id, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/escalate", response_model=IncidentOut)
def escalate_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    updated = IncidentCommandService.escalate(db, incident_id, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.patch("/{incident_id}/false-positive", response_model=IncidentOut)
def false_positive_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    updated = IncidentCommandService.false_positive(db, incident_id, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.delete("/{incident_id}", status_code=204)
def delete_incident(
    incident_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    del current_user
    if not IncidentService.delete(db, incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")
