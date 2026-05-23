"""User request/response schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator

from ..utils.security import validate_password_strength


class UserBase(BaseModel):
    name: str
    email: str
    role: str
    status: str = "Active"


class UserCreate(UserBase):
    id: str
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            validate_password_strength(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            validate_password_strength(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v


class UserOut(UserBase):
    id: str

    class Config:
        from_attributes = True
