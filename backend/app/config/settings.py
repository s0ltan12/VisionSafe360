"""Centralized application configuration via Pydantic BaseSettings.

All runtime configuration is loaded from environment variables (or .env file).
This is the single source of truth — no scattered os.getenv() calls elsewhere.
"""
from __future__ import annotations

import os
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_WEAK_KEYS = {
    "changeme",
    "secret",
    "default",
    "password",
    "visionsafe360-development-secret",
    "this_is_a_strong_minimum_32_characters_key_123",  # shipped default
}


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+pg8000://postgres:postgres@localhost:5432/visionsafe360"

    # ── JWT / Security ────────────────────────────────────────────────
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Redis ─────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_SSL: bool = False

    # ── CORS ──────────────────────────────────────────────────────────
    # Accept comma-separated string from env or a list.
    ALLOWED_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # ── Logging ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    AUDIT_LOG_PATH: str = "backend/logs/audit.log"
    AUDIT_LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    AUDIT_LOG_BACKUP_COUNT: int = 5

    # ── Rate limiting ─────────────────────────────────────────────────
    INCIDENT_RATE_LIMIT_PER_WINDOW: int = 60
    INCIDENT_RATE_LIMIT_WINDOW_SECONDS: int = 60
    # Login brute-force: max 5 attempts per 5 minutes per IP
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # ── Sentry ────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── App ───────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    DEBUG: bool = False

    # ── Pagination defaults ───────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v) -> List[str]:
        """Accept either a list or a comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return list(v)

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        # Allow empty in development — validate_security_config() enforces at startup.
        if not v:
            return v
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        if v.strip().lower() in _WEAK_KEYS:
            raise ValueError(
                "SECRET_KEY matches a known weak/default value. "
                "Generate a strong random key for production."
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
