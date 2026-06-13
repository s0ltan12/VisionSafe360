"""add incident lifecycle columns and timeline events

Revision ID: 20260530_inc_lifecycle
Revises: 20260529_vid_ev
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260530_inc_lifecycle"
down_revision = "20260529_vid_ev"
branch_labels = None
depends_on = None


incident_status = postgresql.ENUM(
    "New",
    "Validating",
    "Active",
    "Acknowledged",
    "Resolved",
    "False Positive",
    "Archived",
    name="incidentstatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    incident_status.create(bind, checkfirst=True)

    op.add_column(
        "incidents",
        sa.Column(
            "status",
            incident_status,
            nullable=False,
            server_default="New",
        ),
    )
    op.add_column("incidents", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("acknowledged_by", sa.String(), nullable=True))
    op.add_column("incidents", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("resolved_by", sa.String(), nullable=True))
    op.add_column("incidents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "incidents",
        sa.Column("escalation_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])

    op.create_table(
        "incident_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("incident_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_events_created_at", "incident_events", ["created_at"])
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])

    op.alter_column("incidents", "status", server_default=None)
    op.alter_column("incidents", "escalation_count", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_incident_events_incident_id", table_name="incident_events")
    op.drop_index("ix_incident_events_created_at", table_name="incident_events")
    op.drop_table("incident_events")

    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_column("incidents", "escalation_count")
    op.drop_column("incidents", "duration_seconds")
    op.drop_column("incidents", "archived_at")
    op.drop_column("incidents", "resolved_by")
    op.drop_column("incidents", "resolved_at")
    op.drop_column("incidents", "acknowledged_by")
    op.drop_column("incidents", "acknowledged_at")
    op.drop_column("incidents", "validated_at")
    op.drop_column("incidents", "started_at")
    op.drop_column("incidents", "status")
    incident_status.drop(op.get_bind(), checkfirst=True)
