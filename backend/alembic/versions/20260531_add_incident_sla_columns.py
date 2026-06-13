"""add incident SLA breach columns

Revision ID: 20260531_incident_sla
Revises: 20260531_alert_event_frame
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op


revision = "20260531_incident_sla"
down_revision = "20260531_alert_event_frame"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_breached_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_ack_breached_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_resolution_breached_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS sla_breach_count INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS sla_breach_count")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS sla_resolution_breached_at")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS sla_ack_breached_at")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS sla_breached_at")
