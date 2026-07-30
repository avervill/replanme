"""Clean Replanme v1 baseline.

Revision ID: 20260731_0001
Revises:
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "google_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("scopes", sa.String(500), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_google_connections_user_id", "google_connections", ["user_id"], unique=True)

    op.create_table(
        "planning_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("energy_windows", sa.JSON(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_planning_profiles_user_id", "planning_profiles", ["user_id"], unique=True)

    op.create_table(
        "long_term_memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_long_term_memories_user_id", "long_term_memories", ["user_id"], unique=True)

    op.create_table(
        "planning_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("route", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="started", nullable=False),
        sa.Column("model_used", sa.String(128), nullable=True),
        sa.Column("plan_snapshot", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_planning_runs_user_id", "planning_runs", ["user_id"])

    op.create_table(
        "calendar_action_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_calendar_action_audit_user_id", "calendar_action_audit", ["user_id"])
    op.create_index("ix_calendar_action_audit_plan_id", "calendar_action_audit", ["plan_id"])
    op.create_index("ix_calendar_action_audit_idempotency_key", "calendar_action_audit", ["idempotency_key"])


def downgrade() -> None:
    op.drop_table("calendar_action_audit")
    op.drop_table("planning_runs")
    op.drop_table("long_term_memories")
    op.drop_table("planning_profiles")
    op.drop_table("google_connections")
    op.drop_table("users")
