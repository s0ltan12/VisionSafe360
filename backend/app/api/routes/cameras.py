"""Camera routes with pagination."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...config.settings import settings
from ...schemas import CameraCreate, CameraOut, CameraUpdate, PaginatedResponse
from ...services.camera_service import CameraService
from ...utils.security import get_current_user

router = APIRouter(
    prefix="/cameras",
    tags=["cameras"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=List[CameraOut])
def get_cameras(db: Session = Depends(get_db)):
    """Return all cameras (no pagination needed — camera counts are small)."""
    items, _ = CameraService.list(db, skip=0, limit=10_000)
    return items


@router.post("", response_model=CameraOut, status_code=201)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    return CameraService.create(db, payload)


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: str, payload: CameraUpdate, db: Session = Depends(get_db)):
    updated = CameraService.update(db, camera_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Camera not found")
    return updated


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    if not CameraService.delete(db, camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")