"""User management routes."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...schemas import UserCreate, UserOut, UserUpdate
from ...services.auth_service import UserService
from ...utils.security import get_current_user

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=List[UserOut])
def get_users(db: Session = Depends(get_db)):
    """Return all users (admin UI; counts are small so no pagination needed)."""
    return UserService.list(db)


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    try:
        return UserService.create(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)):
    try:
        updated = UserService.update(db, user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, db: Session = Depends(get_db)):
    if not UserService.delete(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")