"""add planning credits and analytics

Revision ID: 20260510_0001
Revises: 20260506_0001
Create Date: 2026-05-10
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260510_0001"
down_revision = "20260506_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("planning_credits", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("credits_last_refilled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("subscription_provider", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.execute("UPDATE users SET planning_credits = 20 WHERE planning_credits = 0")
    op.execute("UPDATE users SET subscription_status = 'none' WHERE subscription_status = 'inactive'")

    op.create_table(
        "planning_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("intent", sa.String(length=128), nullable=True),
        sa.Column("feature", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="started", nullable=False),
        sa.Column("estimated_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("credits_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_planning_requests_user_id"), "planning_requests", ["user_id"], unique=False)

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=True),
        sa.Column("related_planning_request_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_credit_transactions_user_id"), "credit_transactions", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_credit_transactions_related_planning_request_id"),
        "credit_transactions",
        ["related_planning_request_id"],
        unique=False,
    )

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analytics_events_event_name"), "analytics_events", ["event_name"], unique=False)
    op.create_index(op.f("ix_analytics_events_user_id"), "analytics_events", ["user_id"], unique=False)

    connection = op.get_bind()
    users = connection.execute(sa.text("SELECT id FROM users WHERE planning_credits = 20")).fetchall()
    credit_transactions = sa.table(
        "credit_transactions",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("amount", sa.Integer()),
        sa.column("balance_before", sa.Integer()),
        sa.column("balance_after", sa.Integer()),
        sa.column("type", sa.String()),
        sa.column("reason", sa.Text()),
    )
    if users:
        op.bulk_insert(
            credit_transactions,
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": row.id,
                    "amount": 20,
                    "balance_before": 0,
                    "balance_after": 20,
                    "type": "signup_bonus",
                    "reason": "Existing user signup planning credits",
                }
                for row in users
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_analytics_events_user_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_event_name"), table_name="analytics_events")
    op.drop_table("analytics_events")
    op.drop_index(op.f("ix_credit_transactions_related_planning_request_id"), table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_user_id"), table_name="credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_index(op.f("ix_planning_requests_user_id"), table_name="planning_requests")
    op.drop_table("planning_requests")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "subscription_provider")
    op.drop_column("users", "is_admin")
    op.drop_column("users", "credits_last_refilled_at")
    op.drop_column("users", "planning_credits")
