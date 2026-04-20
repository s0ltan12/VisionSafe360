"""add user password hash

Revision ID: 0002_add_user_password_hash
Revises: 0001_initial
Create Date: 2026-04-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_user_password_hash"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))


def downgrade() -> None:
	op.drop_column("users", "password_hash")