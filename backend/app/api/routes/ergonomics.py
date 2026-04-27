"""Ergonomics API routes (was previously an empty file)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...config.settings import settings
from ...schemas import ErgonomicRecordCreate, ErgonomicRecordOut, PaginatedResponse
from ...services.ergonomic_service import ErgonomicService
from ...utils.security import get_current_user

router = APIRouter(
    prefix="/ergonomics",
    tags=["ergonomics"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=PaginatedResponse[ErgonomicRecordOut])
def list_ergonomic_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    camera_id: str | None = Query(None, description="Filter by camera ID"),
    db: Session = Depends(get_db),
):
    """List ergonomic risk records, newest first."""
    items, total = ErgonomicService.list(db, skip=skip, limit=limit, camera_id=camera_id)
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit, has_more=(skip + limit) < total)


@router.get("/stats")
def get_ergonomic_stats(db: Session = Depends(get_db)):
    """Summary statistics for the Ergonomics dashboard page."""
    return ErgonomicService.get_stats(db)


@router.post("", response_model=ErgonomicRecordOut, status_code=201)
def create_ergonomic_record(payload: ErgonomicRecordCreate, db: Session = Depends(get_db)):
    """Ingest an ergonomic record from the edge AI pipeline."""
    return ErgonomicService.create(db, payload)
