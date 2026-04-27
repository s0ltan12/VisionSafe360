"""Alert routes with pagination."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...config.settings import settings
from ...schemas import AlertCreate, AlertOut, AlertUpdate, PaginatedResponse
from ...services.alert_service import AlertService
from ...utils.security import get_current_user

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


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
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )


@router.get("/all", response_model=List[AlertOut])
def get_all_alerts(db: Session = Depends(get_db)):
    """Return all alerts without pagination (used by legacy dashboard)."""
    items, _ = AlertService.list(db, skip=0, limit=10_000)
    return items


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = AlertService.get(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("", response_model=AlertOut, status_code=201)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    return AlertService.create(db, payload)


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert(alert_id: str, payload: AlertUpdate, db: Session = Depends(get_db)):
    updated = AlertService.update(db, alert_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    return updated


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: str, db: Session = Depends(get_db)):
    if not AlertService.delete(db, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")