"""Security helpers: JWT, password hashing, RBAC, password validation."""

import re
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..config.database import get_db
from ..config.settings import settings
from ..models import User

# ── Constants pulled from centralized settings ──────────────────────
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
MIN_SECRET_KEY_LENGTH = 32

WEAK_SECRET_KEY_VALUES = {
    "changeme",
    "secret",
    "default",
    "password",
    "visionsafe360-development-secret",
    "this_is_a_strong_minimum_32_characters_key_123",
}

ROLE_ALIASES = {
    "admin": "admin",
    "administrator": "admin",
    "operator": "operator",
    "safety engineer": "operator",
    "safety_engineer": "operator",
    "viewer": "viewer",
    "data analyst": "viewer",
    "data_analyst": "viewer",
}

ROLE_STORAGE_NAMES = {
    "admin": "Admin",
    "operator": "Safety Engineer",
    "viewer": "Data Analyst",
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class OAuth2PasswordBearerWithQuery(OAuth2PasswordBearer):
    def __init__(self, tokenUrl: str):
        super().__init__(tokenUrl=tokenUrl, auto_error=False)

    async def __call__(self, request: Request) -> str | None:
        token = await super().__call__(request)
        if not token:
            token = request.query_params.get("token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return token

oauth2_scheme = OAuth2PasswordBearerWithQuery(tokenUrl="/api/auth/login")


# ── Startup validation ───────────────────────────────────────────────

def validate_security_config() -> None:
    """Raise RuntimeError if security config is unsafe."""
    key = settings.SECRET_KEY
    if not key or not key.strip():
        raise RuntimeError(
            "SECRET_KEY must be set to a strong value. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters")
    if key.strip().lower() in WEAK_SECRET_KEY_VALUES:
        raise RuntimeError(
            "SECRET_KEY is too weak or is a known default value. "
            "Generate a unique high-entropy value for production."
        )


# ── Role helpers ─────────────────────────────────────────────────────

def normalize_role(role: str | None) -> str:
    if role is None:
        return ""
    cleaned = role.strip().lower().replace("-", " ")
    return ROLE_ALIASES.get(cleaned, cleaned)


def storage_role(role: str | None) -> str:
    canonical = normalize_role(role)
    return ROLE_STORAGE_NAMES.get(canonical, role or "")


# ── Password helpers ─────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> str:
    """Enforce minimum password policy.

    Rules:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit

    Returns the password unchanged if valid; raises ValueError otherwise.
    """
    errors: list[str] = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter")
    if not re.search(r"\d", password):
        errors.append("at least one digit")
    if errors:
        raise ValueError(f"Password must contain: {', '.join(errors)}")
    return password


# ── JWT helpers ──────────────────────────────────────────────────────

def _require_secret_key() -> str:
    validate_security_config()
    return settings.SECRET_KEY


def create_access_token(subject: str, role: str | None = None) -> str:
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expires_at = datetime.now(timezone.utc) + expires_delta
    payload: dict = {"sub": subject, "exp": expires_at, "type": "access"}
    if role is not None:
        payload["role"] = normalize_role(role)
    return jwt.encode(payload, _require_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expires_delta = timedelta(days=30)
    expires_at = datetime.now(timezone.utc) + expires_delta
    payload: dict = {"sub": subject, "exp": expires_at, "type": "refresh"}
    return jwt.encode(payload, _require_secret_key(), algorithm=ALGORITHM)


def get_user_from_token(token: str, db: Session, token_type: str = "access") -> User | None:
    try:
        payload = jwt.decode(token, _require_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != token_type and token_type != "any":
            return None
        email: str | None = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
    return db.query(User).filter(User.email == email).first()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = get_user_from_token(token, db)
    if user is None:
        raise credentials_exception
    return user
