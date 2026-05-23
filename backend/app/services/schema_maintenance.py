"""Small startup schema fixes for demo deployments.

Alembic remains the right long-term migration tool. This helper keeps the
graduation-project Docker demo self-healing when existing local databases need
new alert lifecycle columns.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("visionsafe.schema")


def ensure_alert_lifecycle_schema(engine: Engine) -> None:
    """Ensure Phase 1 alert lifecycle fields exist on existing databases."""

    if engine.dialect.name != "postgresql":
        return

    statements = [
        "ALTER TYPE severity ADD VALUE IF NOT EXISTS 'Critical'",
        "ALTER TYPE status ADD VALUE IF NOT EXISTS 'Archived'",
        "ALTER TYPE status ADD VALUE IF NOT EXISTS 'False Positive'",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS area_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS area_name VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS zone_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS zone_name VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS location_description TEXT",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_by_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_by VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_by_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS archived_by VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS archived_by_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS false_positive_by VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS false_positive_by_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS false_positive_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS area_id VARCHAR",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS area_name VARCHAR",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS zone_id VARCHAR",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS zone_name VARCHAR",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS location_description TEXT",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS supported_ai_capabilities JSON",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS severity_profile VARCHAR",
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

    inspector = inspect(engine)
    if "alert_events" in inspector.get_table_names():
        return

    logger.info("alert_events table missing; Base.metadata.create_all will create it")
