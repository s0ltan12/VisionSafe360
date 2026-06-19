"""Alert routes with pagination."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...config.settings import settings
from ...api.websocket.ws_notifications import notification_ws_manager
from ...models import User
from ...schemas import AlertCreate, AlertEventOut, AlertOut, AlertUpdate, PaginatedResponse
from ...services.alert_service import AlertService
from ...services.notification_dispatch_service import NotificationDispatchService
from ...utils.permissions import require_roles

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_roles("admin", "operator", "viewer"))],
)


def _to_list_dto(items):
    """List endpoints must not embed MP4 base64 — clients fetch /alerts/{id} for video.

    Convert ORM rows to detached AlertOut models, then null out the video field
    so we never touch the persisted column.
    """
    out = []
    for a in items:
        dto = AlertOut.model_validate(a, from_attributes=True)
        dto.video_evidence = None
        out.append(dto)
    return out


@router.get("", response_model=PaginatedResponse[AlertOut])
def get_alerts(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Maximum records to return",
    ),
    db: Session = Depends(get_db),
):
    items, total = AlertService.list(db, skip=skip, limit=limit)
    return PaginatedResponse(
        items=_to_list_dto(items),
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )


@router.get("/all", response_model=List[AlertOut])
def get_all_alerts(db: Session = Depends(get_db)):
    """Return all alerts without pagination (used by legacy dashboard)."""
    items, _ = AlertService.list(db, skip=0, limit=10_000)
    return _to_list_dto(items)


@router.get("/{alert_id}/events", response_model=List[AlertEventOut])
def get_alert_events(alert_id: str, db: Session = Depends(get_db)):
    alert = AlertService.get(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertService.list_events(db, alert_id)


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = AlertService.get(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post(
    "",
    response_model=AlertOut,
    status_code=201,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    return AlertService.create(db, payload)


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: str,
    payload: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    updated = AlertService.update(db, alert_id, payload, actor=current_user)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")

    notification = NotificationDispatchService.record_alert_notification(
        db,
        alert=updated,
        action="alert_updated",
        message=f"{updated.id}: {updated.type} alert details updated by {current_user.name}",
    )
    db.commit()
    db.refresh(notification)

    await notification_ws_manager.broadcast({
        "type": "notification",
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "notification_type": notification.type,
        "severity": updated.severity.value if hasattr(updated.severity, "value") else str(updated.severity),
        "source": notification.source,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    })
    return updated


@router.delete("/{alert_id}", status_code=204)
def delete_alert(
    alert_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    del current_user
    if not AlertService.delete(db, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
