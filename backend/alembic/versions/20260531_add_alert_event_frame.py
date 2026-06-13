"""add exact event frame to alerts

Revision ID: 20260531_alert_event_frame
Revises: 20260530_inc_lifecycle
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op


revision = "20260531_alert_event_frame"
down_revision = "20260530_inc_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS event_frame TEXT")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS track_id INTEGER")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_number INTEGER")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_width INTEGER")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS frame_height INTEGER")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS evidence_kind VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS evidence_kind")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS frame_height")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS frame_width")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS frame_number")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS track_id")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS event_frame")
