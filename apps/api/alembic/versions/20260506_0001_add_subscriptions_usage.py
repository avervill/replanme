"""add subscriptions and usage limits

Revision ID: 20260506_0001
Revises: 20260424_0001
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0001"
down_revision = "20260424_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("plan", sa.String(length=16), server_default="free", nullable=False))
    op.add_column(
        "users",
        sa.Column("subscription_status", sa.String(length=32), server_default="inactive", nullable=False),
    )
    op.add_column("users", sa.Column("subscription_provider_customer_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("subscription_current_period_end", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "usage_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ai_actions_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("weekly_plans_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("image_imports_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("voice_inputs_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("monthly_plans_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("smart_reschedules_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("energy_schedules_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recurring_plans_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "period_start", "period_end", name="uq_usage_limits_user_period"),
    )
    op.create_index(op.f("ix_usage_limits_user_id"), "usage_limits", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_limits_user_id"), table_name="usage_limits")
    op.drop_table("usage_limits")
    op.drop_column("users", "subscription_current_period_end")
    op.drop_column("users", "subscription_provider_customer_id")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "plan")
