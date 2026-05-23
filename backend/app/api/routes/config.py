"""System configuration backend API.

Stores and retrieves runtime settings as key-value pairs.
The dashboard Configuration page now has real backend support.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...models import SystemConfig
from ...schemas import SystemConfigCreate, SystemConfigOut, SystemConfigUpdate
from ...utils.permissions import require_roles

router = APIRouter(
    prefix="/config",
    tags=["configuration"],
    dependencies=[Depends(require_roles("admin"))],
)


@router.get("", response_model=List[SystemConfigOut])
def list_config(db: Session = Depends(get_db)):
    """Return all system configuration key-value pairs."""
    return db.query(SystemConfig).order_by(SystemConfig.key).all()


@router.get("/{key}", response_model=SystemConfigOut)
def get_config(key: str, db: Session = Depends(get_db)):
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")
    return row


@router.put("/{key}", response_model=SystemConfigOut)
def upsert_config(key: str, payload: SystemConfigUpdate, db: Session = Depends(get_db)):
    """Create or update a configuration entry."""
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None:
        row = SystemConfig(key=key, value=payload.value, value_type="string")
        db.add(row)
    else:
        row.value = payload.value
    if payload.description is not None:
        row.description = payload.description
    db.commit()
    db.refresh(row)
    return row


@router.post("", response_model=SystemConfigOut, status_code=201)
def create_config(payload: SystemConfigCreate, db: Session = Depends(get_db)):
    existing = db.query(SystemConfig).filter(SystemConfig.key == payload.key).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Config key '{payload.key}' already exists")
    row = SystemConfig(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{key}", status_code=204)
def delete_config(key: str, db: Session = Depends(get_db)):
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")
    db.delete(row)
    db.commit()
