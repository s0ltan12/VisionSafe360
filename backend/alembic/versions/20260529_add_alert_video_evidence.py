"""add video evidence to alerts table

Revision ID: 20260529_vid_ev
Revises: 20260515_ai_meta
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260529_vid_ev"
down_revision = "20260515_ai_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("video_evidence", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "video_evidence")
