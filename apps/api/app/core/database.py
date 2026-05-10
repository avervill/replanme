"""SQLAlchemy async engine & session factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, future=True, echo=settings.debug)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables from model metadata (dev convenience).

    In production, rely on Alembic migrations instead.
    """
    from app.models import Base  # noqa: F811

    logger.info("Running init_db - creating tables if missing")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _ensure_billing_columns(connection)


async def _ensure_billing_columns(connection) -> None:
    """Dev-only compatibility for existing local databases.

    ``create_all`` creates missing tables but does not add new columns to an
    existing table. Keep local Docker/SQLite databases aligned with the current
    user model so auth does not fail before Alembic is run.
    """

    def existing_user_columns(sync_connection) -> set[str]:
        inspector = inspect(sync_connection)
        if not inspector.has_table("users"):
            return set()
        return {column["name"] for column in inspector.get_columns("users")}

    existing = await connection.run_sync(existing_user_columns)
    if not existing:
        return

    period_end_type = (
        "TIMESTAMP WITH TIME ZONE"
        if connection.dialect.name == "postgresql"
        else "DATETIME"
    )
    boolean_false = "false" if connection.dialect.name == "postgresql" else "0"
    columns = {
        "plan": "ALTER TABLE users ADD COLUMN plan VARCHAR(16) NOT NULL DEFAULT 'free'",
        "planning_credits": "ALTER TABLE users ADD COLUMN planning_credits INTEGER NOT NULL DEFAULT 0",
        "credits_last_refilled_at": f"ALTER TABLE users ADD COLUMN credits_last_refilled_at {period_end_type}",
        "is_admin": f"ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT {boolean_false}",
        "subscription_status": (
            "ALTER TABLE users ADD COLUMN subscription_status "
            "VARCHAR(32) NOT NULL DEFAULT 'none'"
        ),
        "subscription_provider": "ALTER TABLE users ADD COLUMN subscription_provider VARCHAR(32)",
        "subscription_provider_customer_id": (
            "ALTER TABLE users ADD COLUMN subscription_provider_customer_id VARCHAR(255)"
        ),
        "subscription_current_period_end": (
            f"ALTER TABLE users ADD COLUMN subscription_current_period_end {period_end_type}"
        ),
        "stripe_customer_id": "ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255)",
        "stripe_subscription_id": "ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR(255)",
    }
    for column, statement in columns.items():
        if column not in existing:
            logger.info("Adding missing users.%s column", column)
            await connection.execute(text(statement))
