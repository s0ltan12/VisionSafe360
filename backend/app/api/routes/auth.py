"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...schemas import LoginRequest, TokenResponse, UserOut
from ...services.auth_service import AuthService
from ...utils.security import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
	try:
		token = AuthService.login(db, payload)
	except HTTPException:
		raise
	return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user = Depends(get_current_user)):
	return current_user