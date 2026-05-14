"""add onboarding fields to users

Revision ID: 20260514_0001
Revises: 20260510_0001
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260514_0001"
down_revision = "20260510_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_completed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("onboarding_skipped", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("onboarding_data", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE users SET onboarding_completed = true, onboarding_completed_at = CURRENT_TIMESTAMP "
        "WHERE onboarding_completed = false"
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_data")
    op.drop_column("users", "onboarding_skipped")
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "onboarding_completed")
