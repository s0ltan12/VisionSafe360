"""add camera safety zones

Revision ID: 20260609_add_camera_safety_zones
Revises: 20260605_add_overspeed_hazard_type
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_add_camera_safety_zones"
down_revision = "20260605_add_overspeed_hazard_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_safety_zones",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("zone_type", sa.String(), nullable=False),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column("coordinate_space", sa.String(), nullable=False, server_default="source_pixels"),
        sa.Column("source_width", sa.Integer(), nullable=False),
        sa.Column("source_height", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(), nullable=False, server_default="#f97316"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(), nullable=True),
        sa.Column("updated_by_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_camera_safety_zones_camera_enabled", "camera_safety_zones", ["camera_id", "enabled"])
    op.create_index("ix_camera_safety_zones_camera_type", "camera_safety_zones", ["camera_id", "zone_type"])
    op.create_index("ix_camera_safety_zones_deleted_at", "camera_safety_zones", ["deleted_at"])

    op.create_table(
        "camera_safety_zone_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("zone_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("object_class", sa.String(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("stable_object_key", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("duration_inside_sec", sa.Float(), nullable=True),
        sa.Column("occupancy_count", sa.Integer(), nullable=True),
        sa.Column("frame_number", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("anchor_point", sa.JSON(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("alert_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.ForeignKeyConstraint(["zone_id"], ["camera_safety_zones.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_camera_safety_zone_events_camera_time", "camera_safety_zone_events", ["camera_id", "occurred_at"])
    op.create_index("ix_camera_safety_zone_events_zone_time", "camera_safety_zone_events", ["zone_id", "occurred_at"])
    op.create_index("ix_camera_safety_zone_events_type_time", "camera_safety_zone_events", ["event_type", "occurred_at"])
    op.create_index("ix_camera_safety_zone_events_stable_object_time", "camera_safety_zone_events", ["stable_object_key", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_camera_safety_zone_events_stable_object_time", table_name="camera_safety_zone_events")
    op.drop_index("ix_camera_safety_zone_events_type_time", table_name="camera_safety_zone_events")
    op.drop_index("ix_camera_safety_zone_events_zone_time", table_name="camera_safety_zone_events")
    op.drop_index("ix_camera_safety_zone_events_camera_time", table_name="camera_safety_zone_events")
    op.drop_table("camera_safety_zone_events")
    op.drop_index("ix_camera_safety_zones_deleted_at", table_name="camera_safety_zones")
    op.drop_index("ix_camera_safety_zones_camera_type", table_name="camera_safety_zones")
    op.drop_index("ix_camera_safety_zones_camera_enabled", table_name="camera_safety_zones")
    op.drop_table("camera_safety_zones")
