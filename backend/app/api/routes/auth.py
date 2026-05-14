"""Authentication routes with login rate limiting."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...schemas import LoginRequest, TokenResponse, UserOut
from ...services.auth_service import AuthService
from ...services.login_rate_limit_service import login_rate_limit_service
from ...utils.audit_logger import audit_event, ensure_request_id, get_client_ip_from_request
from ...utils.security import create_access_token, create_refresh_token, get_current_user, get_user_from_token, normalize_role
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("visionsafe.auth")

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate and return a JWT access token.

    Protected against brute force via per-IP sliding-window rate limiting.
    """
    request_id = ensure_request_id(
        getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    )
    ip_address = getattr(request.state, "client_ip", None) or get_client_ip_from_request(request)

    # ── Rate limiting ─────────────────────────────────────────────────
    allowed, retry_after = login_rate_limit_service.check_and_consume(ip_address)
    if not allowed:
        logger.warning(
            "login rate limited",
            extra={"event": "login_rate_limited", "ip": ip_address, "email": payload.email},
        )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )

    # ── Authentication ────────────────────────────────────────────────
    user = AuthService.authenticate(db, payload)
    if not user:
        audit_event(
            "login",
            user_id=None,
            ip_address=ip_address,
            request_id=request_id,
            outcome="failure",
            email=payload.email,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful login — reset rate limit counter for this IP
    login_rate_limit_service.reset(ip_address)

    token = create_access_token(subject=user.email, role=normalize_role(user.role))
    refresh = create_refresh_token(subject=user.email)
    audit_event(
        "login",
        user_id=user.id,
        ip_address=ip_address,
        request_id=request_id,
        outcome="success",
        role=normalize_role(user.role),
    )
    return TokenResponse(access_token=token, refresh_token=refresh)

@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    user = get_user_from_token(payload.refresh_token, db, token_type="refresh")
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    
    token = create_access_token(subject=user.email, role=normalize_role(user.role))
    new_refresh = create_refresh_token(subject=user.email)
    return TokenResponse(access_token=token, refresh_token=new_refresh)

@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user