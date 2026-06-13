"""Small startup schema fixes for demo deployments.

Alembic remains the right long-term migration tool. This helper keeps the
graduation-project Docker demo self-healing when existing local databases need
new alert lifecycle columns.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.engine import Engine

logger = logging.getLogger("visionsafe.schema")


# Source of truth: backend/app/models/enums.py. Kept in sync manually because
# ORM columns use create_type=False, so Base.metadata.create_all does not
# materialize these PG types — we have to do it here on first boot.
_ENUM_TYPES: list[tuple[str, list[str]]] = [
    ("hazardtype", ["PPE", "Fall", "Proximity", "Overspeed", "Ergonomics", "Intrusion"]),
    ("severity",   ["Critical", "High", "Medium", "Low"]),
    ("status",     ["New", "Notified", "Acknowledged", "In Investigation",
                    "Resolved", "Archived", "False Positive", "Dismissed", "Active"]),
    ("incidentstatus", ["New", "Validating", "Active", "Acknowledged",
                        "Resolved", "False Positive", "Archived"]),
    ("userrole",   ["Admin", "Safety Engineer", "Data Analyst"]),
    ("risklevel",  ["Low", "Medium", "High", "Critical"]),
]


def ensure_enum_types(engine: Engine) -> None:
    """Create the PG enum types referenced by ORM models if they're missing.

    Idempotent: ENUM.create(checkfirst=True) is a no-op when the type already
    exists. Must run BEFORE Base.metadata.create_all because every table that
    has an enum column declares it with create_type=False.
    """

    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        for name, values in _ENUM_TYPES:
            ENUM(*values, name=name, create_type=True).create(conn, checkfirst=True)


def ensure_alert_lifecycle_schema(engine: Engine) -> None:
    """Apply additive enum-value and column upgrades for older databases.

    Each statement runs in its own transaction so one failure (e.g. a column
    that has already been dropped manually) does not roll back the others —
    most importantly the `video_evidence` column the dashboard depends on.
    """

    if engine.dialect.name != "postgresql":
        return

    statements = [
        "ALTER TYPE severity ADD VALUE IF NOT EXISTS 'Critical'",
        "ALTER TYPE hazardtype ADD VALUE IF NOT EXISTS 'Overspeed'",
        "ALTER TYPE status ADD VALUE IF NOT EXISTS 'Archived'",
        "ALTER TYPE status ADD VALUE IF NOT EXISTS 'False Positive'",
        "ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'Validating'",
        "ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'Active'",
        "ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'Acknowledged'",
        "ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'Resolved'",
        "ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'False Positive'",
        "ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'Archived'",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS incident_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS area_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS area_name VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS zone_id VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS zone_name VARCHAR",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS location_description TEXT",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS event_frame TEXT",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS video_evidence TEXT",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS track_id INTEGER",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_number INTEGER",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_width INTEGER",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_height INTEGER",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS evidence_kind VARCHAR",
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
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS status incidentstatus NOT NULL DEFAULT 'New'",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS resolved_by VARCHAR",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_breached_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_ack_breached_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_resolution_breached_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_breach_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS duration_seconds INTEGER",
        "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS escalation_count INTEGER NOT NULL DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS ix_alerts_incident_id ON alerts (incident_id)",
        "CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents (status)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_alerts_incident_id_incidents'
            ) THEN
                ALTER TABLE alerts
                ADD CONSTRAINT fk_alerts_incident_id_incidents
                FOREIGN KEY (incident_id) REFERENCES incidents(id);
            END IF;
        END
        $$;
        """,
    ]

    for statement in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as exc:
            logger.warning("schema maintenance step skipped: %s — %s", statement, exc)

    inspector = inspect(engine)
    if "alert_events" in inspector.get_table_names():
        return

    logger.info("alert_events table missing; Base.metadata.create_all will create it")
