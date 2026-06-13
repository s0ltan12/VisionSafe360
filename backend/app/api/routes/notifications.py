"""Notification REST routes — CRUD + mark-as-read."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...config.settings import settings
from ...models import Notification
from ...schemas import NotificationCreate, NotificationMarkRead, NotificationOut, PaginatedResponse
from ...utils.security import get_current_user
from ...utils.security import normalize_role
from ...utils.permissions import require_roles
from ...api.websocket.ws_notifications import notification_ws_manager

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_roles("admin", "operator", "viewer"))],
)


@router.get("", response_model=PaginatedResponse[NotificationOut])
def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(Notification).filter(
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None))
    )
    if unread_only:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    total = q.count()
    items = q.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit, has_more=(skip + limit) < total)


@router.post(
    "",
    response_model=NotificationOut,
    status_code=201,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
async def create_notification(payload: NotificationCreate, db: Session = Depends(get_db)):
    """Create a notification and broadcast it via WebSocket."""
    row = Notification(
        id=payload.id or str(uuid.uuid4()),
        user_id=payload.user_id,
        title=payload.title,
        message=payload.message,
        type=payload.type,
        source=payload.source,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    await notification_ws_manager.broadcast({
        "type": "notification",
        "id": row.id,
        "title": row.title,
        "message": row.message,
        "notification_type": row.type,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    })
    return row


@router.post("/mark-read", status_code=204)
def mark_as_read(payload: NotificationMarkRead, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    db.query(Notification).filter(
        Notification.id.in_(payload.ids),
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None)),
    ).update(
        {"is_read": True}, synchronize_session="fetch"
    )
    db.commit()


@router.post("/mark-all-read", status_code=204)
def mark_all_read(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    db.query(Notification).filter(
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None))
    ).update({"is_read": True}, synchronize_session="fetch")
    db.commit()


@router.delete("/{notification_id}", status_code=204)
def delete_notification(notification_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = db.query(Notification).filter(
        Notification.id == notification_id,
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None)),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.user_id is None and normalize_role(current_user.role) != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to delete broadcast notifications")
    db.delete(row)
    db.commit()
