"""Incident routes."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...api.websocket.ws_handler import incident_ws_manager, serialize_incident
from ...services.monitoring_service import monitoring_service
from ...services.rate_limit_service import rate_limit_service
from ...schemas import IncidentCreate, IncidentOut, IncidentUpdate
from ...services.incident_service import IncidentService
from ...utils.security import get_current_user

router = APIRouter(prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger("visionsafe.incidents")


@router.get("", response_model=List[IncidentOut])
def get_incidents(db: Session = Depends(get_db)):
	return IncidentService.list(db)


@router.post("", response_model=IncidentOut, status_code=201)
async def create_incident(
	payload: IncidentCreate,
	db: Session = Depends(get_db),
	x_source_id: str | None = Header(default=None),
	x_camera_id: str | None = Header(default=None),
):
	source_id = (x_source_id or x_camera_id or payload.zone or "unknown").strip() or "unknown"
	allowed, retry_after = rate_limit_service.check_and_consume(source_id)
	if not allowed:
		monitoring_service.record_rate_limited(source_id)
		logger.warning(
			"incident rate limited",
			extra={
				"event": "incident_rate_limited",
				"source_id": source_id,
				"incident_id": payload.id,
			},
		)
		raise HTTPException(
			status_code=429,
			detail="Incident ingestion rate limit exceeded",
			headers={"Retry-After": str(retry_after)},
		)

	existing = IncidentService.get(db, payload.id)
	if existing is not None:
		logger.info(
			"duplicate incident rejected",
			extra={
				"event": "incident_duplicate",
				"source_id": source_id,
				"incident_id": payload.id,
			},
		)
		raise HTTPException(status_code=409, detail=f"Incident with id '{payload.id}' already exists")

	try:
		incident = IncidentService.create(db, payload)
	except IntegrityError as exc:
		db.rollback()
		logger.info(
			"duplicate incident rejected by DB",
			extra={
				"event": "incident_duplicate_db",
				"source_id": source_id,
				"incident_id": payload.id,
			},
		)
		raise HTTPException(status_code=409, detail=f"Incident with id '{payload.id}' already exists") from exc

	monitoring_service.record_incident(source_id)
	logger.info(
		"incident created",
		extra={
			"event": "incident_created",
			"source_id": source_id,
			"incident_id": incident.id,
		},
	)

	await incident_ws_manager.broadcast(
		{
			"type": "incident_created",
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"incident": serialize_incident(incident),
		}
	)
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