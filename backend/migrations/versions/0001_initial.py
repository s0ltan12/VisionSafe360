"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-04-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

hazard_type_enum = ENUM("PPE", "Fall", "Proximity", "Ergonomics", "Intrusion", name="hazardtype", create_type=False)
severity_enum = ENUM("High", "Medium", "Low", name="severity", create_type=False)
status_enum = ENUM(
	"New",
	"Notified",
	"Acknowledged",
	"In Investigation",
	"Resolved",
	"Dismissed",
	"Active",
	name="status",
	create_type=False,
)
user_role_enum = ENUM("Admin", "Safety Engineer", "Data Analyst", name="userrole", create_type=False)


def _create_enums(connection) -> None:
	hazard_type_enum.create(connection, checkfirst=True)
	severity_enum.create(connection, checkfirst=True)
	status_enum.create(connection, checkfirst=True)
	user_role_enum.create(connection, checkfirst=True)


def _drop_enums(connection) -> None:
	user_role_enum.drop(connection, checkfirst=True)
	status_enum.drop(connection, checkfirst=True)
	severity_enum.drop(connection, checkfirst=True)
	hazard_type_enum.drop(connection, checkfirst=True)


def upgrade() -> None:
	connection = op.get_bind()
	_create_enums(connection)

	op.create_table(
		"alerts",
		sa.Column("id", sa.String(), primary_key=True),
		sa.Column("type", hazard_type_enum, nullable=False),
		sa.Column("severity", severity_enum, nullable=False),
		sa.Column("zone", sa.String(), nullable=False),
		sa.Column("camera", sa.String(), nullable=False),
		sa.Column("timestamp", sa.String(), nullable=False),
		sa.Column("status", status_enum, server_default=sa.text("'New'")),
		sa.Column("description", sa.Text(), nullable=False),
		sa.Column("thumbnail", sa.String(), nullable=False),
		sa.Column("confidence", sa.Float(), nullable=True),
	)

	op.create_table(
		"cameras",
		sa.Column("id", sa.String(), primary_key=True),
		sa.Column("name", sa.String(), nullable=False),
		sa.Column("zone", sa.String(), nullable=False),
		sa.Column("url", sa.String(), nullable=True),
		sa.Column("status", sa.String(), server_default="Online"),
		sa.Column("is_privacy_mode", sa.Boolean(), server_default=sa.text("false")),
		sa.Column("thumbnail", sa.String(), nullable=True),
		sa.Column("fps", sa.Float(), nullable=True),
		sa.Column("health", sa.Float(), nullable=True),
	)

	op.create_table(
		"incidents",
		sa.Column("id", sa.String(), primary_key=True),
		sa.Column("zone", sa.String(), nullable=False),
		sa.Column("classification", sa.String(), nullable=False),
		sa.Column("severity", severity_enum, nullable=False),
		sa.Column("root_cause", sa.Text(), server_default="Under Investigation"),
		sa.Column("corrective_action", sa.Text(), server_default="Pending Review"),
		sa.Column("created_at", sa.String(), nullable=False),
	)

	op.create_table(
		"users",
		sa.Column("id", sa.String(), primary_key=True),
		sa.Column("name", sa.String(), nullable=False),
		sa.Column("email", sa.String(), nullable=False, unique=True),
		sa.Column("role", user_role_enum, nullable=False),
		sa.Column("status", sa.String(), server_default="Active"),
	)


def downgrade() -> None:
	connection = op.get_bind()
	op.drop_table("users")
	op.drop_table("incidents")
	op.drop_table("cameras")
	op.drop_table("alerts")
	_drop_enums(connection)