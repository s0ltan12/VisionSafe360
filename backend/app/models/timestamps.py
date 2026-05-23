"""Timezone-aware timestamp helpers used as SQLAlchemy column defaults."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
