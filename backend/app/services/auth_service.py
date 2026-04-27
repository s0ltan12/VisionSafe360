"""User service and auth placeholders for the active backend."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import User
from ..schemas import LoginRequest, UserCreate, UserUpdate
from ..utils.security import (
    create_access_token,
    hash_password,
    normalize_role,
    storage_role,
    validate_password_strength,
    verify_password,
)


class UserService:
	@staticmethod
	def list(db: Session):
		return db.query(User).all()

	@staticmethod
	def get(db: Session, user_id: str):
		return db.query(User).filter(User.id == user_id).first()

	@staticmethod
	def get_by_email(db: Session, email: str):
		return db.query(User).filter(User.email == email).first()

	@staticmethod
	def create(db: Session, payload: UserCreate):
		if UserService.get_by_email(db, payload.email):
			raise ValueError("Email already registered")
		data = payload.model_dump(exclude={"password"})
		if data.get("role"):
			data["role"] = storage_role(data["role"])
		user = User(**data, password_hash=hash_password(payload.password) if payload.password else None)
		db.add(user)
		db.commit()
		db.refresh(user)
		return user

	@staticmethod
	def update(db: Session, user_id: str, payload: UserUpdate):
		user = UserService.get(db, user_id)
		if not user:
			return None
		if payload.email and payload.email != user.email and UserService.get_by_email(db, payload.email):
			raise ValueError("Email already registered")
		update_data = payload.model_dump(exclude_unset=True)
		password = update_data.pop("password", None)
		if update_data.get("role"):
			update_data["role"] = storage_role(update_data["role"])
		if password:
			user.password_hash = hash_password(password)
		for field, value in update_data.items():
			setattr(user, field, value)
		db.commit()
		db.refresh(user)
		return user

	@staticmethod
	def delete(db: Session, user_id: str) -> bool:
		user = UserService.get(db, user_id)
		if not user:
			return False
		db.delete(user)
		db.commit()
		return True


class AuthService:
	@staticmethod
	def authenticate(db: Session, payload: LoginRequest) -> Optional[User]:
		user = UserService.get_by_email(db, payload.email)
		if not user or not user.password_hash:
			return None
		if not verify_password(payload.password, user.password_hash):
			return None
		return user

	@staticmethod
	def login(db: Session, payload: LoginRequest) -> str:
		user = AuthService.authenticate(db, payload)
		if not user:
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
		return create_access_token(subject=user.email, role=normalize_role(user.role))