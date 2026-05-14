"""add incident and alert camera/worker metadata

Revision ID: 20260515_add_incident_alert_metadata
Revises: 23137d6336b1_initial_migration_create_users_cameras_
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_add_incident_alert_metadata"
down_revision = "23137d6336b1_initial_migration_create_users_cameras_"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column("alerts", sa.Column("camera_id", sa.String(), nullable=True))
	op.add_column("alerts", sa.Column("camera_name", sa.String(), nullable=True))
	op.add_column("alerts", sa.Column("worker_id", sa.String(), nullable=True))
	op.add_column("alerts", sa.Column("worker_gpu_id", sa.String(), nullable=True))
	op.add_column("incidents", sa.Column("camera_id", sa.String(), nullable=True))
	op.add_column("incidents", sa.Column("camera_name", sa.String(), nullable=True))
	op.add_column("incidents", sa.Column("worker_id", sa.String(), nullable=True))
	op.add_column("incidents", sa.Column("worker_gpu_id", sa.String(), nullable=True))

	op.create_index("ix_alerts_camera_id", "alerts", ["camera_id"])
	op.create_index("ix_alerts_worker_id", "alerts", ["worker_id"])
	op.create_index("ix_incidents_camera_id", "incidents", ["camera_id"])
	op.create_index("ix_incidents_worker_id", "incidents", ["worker_id"])


def downgrade() -> None:
	op.drop_index("ix_incidents_worker_id", table_name="incidents")
	op.drop_index("ix_incidents_camera_id", table_name="incidents")
	op.drop_index("ix_alerts_worker_id", table_name="alerts")
	op.drop_index("ix_alerts_camera_id", table_name="alerts")
	op.drop_column("incidents", "worker_gpu_id")
	op.drop_column("incidents", "worker_id")
	op.drop_column("incidents", "camera_name")
	op.drop_column("incidents", "camera_id")
	op.drop_column("alerts", "worker_gpu_id")
	op.drop_column("alerts", "worker_id")
	op.drop_column("alerts", "camera_name")
	op.drop_column("alerts", "camera_id")
