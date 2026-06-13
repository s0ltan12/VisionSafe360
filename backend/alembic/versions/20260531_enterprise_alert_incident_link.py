"""enterprise alert incident link and incident false-positive status

Revision ID: 20260531_alert_incident_link
Revises: 20260531_incident_sla
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op


revision = "20260531_alert_incident_link"
down_revision = "20260531_incident_sla"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'False Positive'")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS incident_id VARCHAR")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_incident_id ON alerts (incident_id)")
    op.create_foreign_key(
        "fk_alerts_incident_id_incidents",
        "alerts",
        "incidents",
        ["incident_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE alerts AS a
        SET incident_id = ae.event_metadata ->> 'incident_id'
        FROM alert_events AS ae
        WHERE a.id = ae.alert_id
          AND a.incident_id IS NULL
          AND ae.event_metadata ->> 'incident_id' IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_alerts_incident_id_incidents", "alerts", type_="foreignkey")
    op.execute("DROP INDEX IF EXISTS ix_alerts_incident_id")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS incident_id")
    # PostgreSQL enum values cannot be dropped safely without recreating the type.
