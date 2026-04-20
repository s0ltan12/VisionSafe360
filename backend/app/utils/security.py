"""Security helpers placeholder."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..config.database import get_db
from ..models import User

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
MIN_SECRET_KEY_LENGTH = 32
WEAK_SECRET_KEY_VALUES = {
	"changeme",
	"secret",
	"default",
	"password",
	"visionsafe360-development-secret",
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def validate_security_config() -> None:
	if not SECRET_KEY or not SECRET_KEY.strip():
		raise RuntimeError("SECRET_KEY must be set to a strong value")

	if len(SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
		raise RuntimeError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters")

	if SECRET_KEY.strip().lower() in WEAK_SECRET_KEY_VALUES:
		raise RuntimeError("SECRET_KEY is too weak; choose a unique high-entropy value")


def _require_secret_key() -> str:
	validate_security_config()
	return SECRET_KEY or ""


def hash_password(password: str) -> str:
	return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
	return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
	expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
	expires_at = datetime.now(timezone.utc) + expires_delta
	return jwt.encode({"sub": subject, "exp": expires_at}, _require_secret_key(), algorithm=ALGORITHM)


def get_user_from_token(token: str, db: Session) -> User | None:
	try:
		payload = jwt.decode(token, _require_secret_key(), algorithms=[ALGORITHM])
		email: str | None = payload.get("sub")
		if email is None:
			return None
	except JWTError:
		return None

	return db.query(User).filter(User.email == email).first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	user = get_user_from_token(token, db)
	if user is None:
		raise credentials_exception
	return user
