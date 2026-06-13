"""add overspeed hazard type

Revision ID: 20260605_add_overspeed_hazard_type
Revises: 20260531_alert_incident_link
Create Date: 2026-06-05
"""

from alembic import op


revision = "20260605_add_overspeed_hazard_type"
down_revision = "20260531_alert_incident_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE hazardtype ADD VALUE IF NOT EXISTS 'Overspeed'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without recreating the type.
    pass
