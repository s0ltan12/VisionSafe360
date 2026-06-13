"""Camera safety zone management and history endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...models import User
from ...schemas.safety_zone import (
    SafetyZoneCreate,
    SafetyZoneEnabledUpdate,
    SafetyZoneEventOut,
    SafetyZoneOut,
    SafetyZoneStatsOut,
    SafetyZoneUpdate,
)
from ...services.safety_zone_service import SafetyZoneService
from ...utils.permissions import require_roles

router = APIRouter(
    tags=["safety-zones"],
    dependencies=[Depends(require_roles("admin", "operator", "viewer"))],
)


@router.get("/cameras/{camera_id}/safety-zones", response_model=list[SafetyZoneOut])
def list_camera_safety_zones(camera_id: str, db: Session = Depends(get_db)):
    return SafetyZoneService.list_for_camera(db, camera_id)


@router.post(
    "/cameras/{camera_id}/safety-zones",
    response_model=SafetyZoneOut,
    status_code=201,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
def create_camera_safety_zone(
    camera_id: str,
    payload: SafetyZoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    return SafetyZoneService.create(db, camera_id, payload, actor_id=current_user.id)


@router.get("/safety-zones/{zone_id}", response_model=SafetyZoneOut)
def get_safety_zone(zone_id: str, db: Session = Depends(get_db)):
    zone = SafetyZoneService.get(db, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Safety zone not found")
    return zone


@router.patch(
    "/safety-zones/{zone_id}",
    response_model=SafetyZoneOut,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
def update_safety_zone(
    zone_id: str,
    payload: SafetyZoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    zone = SafetyZoneService.update(db, zone_id, payload, actor_id=current_user.id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Safety zone not found")
    return zone


@router.patch(
    "/safety-zones/{zone_id}/enabled",
    response_model=SafetyZoneOut,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
def set_safety_zone_enabled(
    zone_id: str,
    payload: SafetyZoneEnabledUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    zone = SafetyZoneService.set_enabled(db, zone_id, payload, actor_id=current_user.id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Safety zone not found")
    return zone


@router.delete(
    "/safety-zones/{zone_id}",
    status_code=204,
    dependencies=[Depends(require_roles("admin", "operator"))],
)
def delete_safety_zone(
    zone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operator")),
):
    if not SafetyZoneService.delete(db, zone_id, actor_id=current_user.id):
        raise HTTPException(status_code=404, detail="Safety zone not found")


@router.get("/safety-zones/{zone_id}/events", response_model=list[SafetyZoneEventOut])
def list_safety_zone_events(
    zone_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return SafetyZoneService.list_events(db, zone_id=zone_id, skip=skip, limit=limit)


@router.get("/cameras/{camera_id}/safety-zone-events", response_model=list[SafetyZoneEventOut])
def list_camera_safety_zone_events(
    camera_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return SafetyZoneService.list_events(db, camera_id=camera_id, skip=skip, limit=limit)


@router.get("/safety-zones/{zone_id}/stats", response_model=SafetyZoneStatsOut)
def get_safety_zone_stats(zone_id: str, db: Session = Depends(get_db)):
    return SafetyZoneService.stats_for_zone(db, zone_id)


@router.get("/cameras/{camera_id}/safety-zone-stats", response_model=list[SafetyZoneStatsOut])
def get_camera_safety_zone_stats(camera_id: str, db: Session = Depends(get_db)):
    return SafetyZoneService.stats_for_camera(db, camera_id)
