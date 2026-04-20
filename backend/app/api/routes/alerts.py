"""Alert routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...schemas import AlertCreate, AlertOut, AlertUpdate
from ...services.alert_service import AlertService
from ...utils.security import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[AlertOut])
def get_alerts(db: Session = Depends(get_db)):
	return AlertService.list(db)


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