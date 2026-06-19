"""add alert event metadata snapshot column

Revision ID: 20260610_add_alert_event_metadata
Revises: 20260609_add_camera_safety_zones
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op


revision = "20260610_add_alert_event_metadata"
down_revision = "20260609_add_camera_safety_zones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS event_metadata JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS event_metadata")
