"""SQLAlchemy async engine & session factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

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

    logger.info("Running init_db – creating tables if missing")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
