"""Authentication schemas — login and JWT payloads."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 480 * 60


class TokenPayload(BaseModel):
    sub: str
    role: Optional[str] = None
