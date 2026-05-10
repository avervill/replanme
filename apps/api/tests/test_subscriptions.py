import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.admin import require_admin
from app.models import Base
from app.models.credit_transaction import CreditTransaction
from app.models.user import User
from app.services.billing_config import FREE_MAX_CREDITS, PRO_MAX_CREDITS
from app.services.credits import (
    adjust_credits,
    grant_credits,
    grant_signup_credits_if_needed,
    maybe_refill_credits,
)
from app.services.subscriptions import FeatureName, PaywallError, commit_usage, reserve_usage


async def _session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'usage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory()


def test_new_user_receives_signup_credits_with_transaction(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="free@example.com")
            db.add(user)
            await db.flush()
            await grant_signup_credits_if_needed(db, user)
            await db.commit()

            assert user.planning_credits == 20
            tx = (
                await db.execute(
                    select(CreditTransaction).where(
                        CreditTransaction.user_id == user.id,
                        CreditTransaction.type == "signup_bonus",
                    )
                )
            ).scalar_one()
            assert tx.amount == 20
            assert tx.balance_before == 0
            assert tx.balance_after == 20
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_free_weekly_refill_caps_at_30(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(
                email="refill@example.com",
                planning_credits=28,
                credits_last_refilled_at=datetime.now(UTC) - timedelta(days=8),
            )
            db.add(user)
            await db.commit()

            await maybe_refill_credits(db, user.id)
            await db.refresh(user)
            assert user.planning_credits == FREE_MAX_CREDITS
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_pro_monthly_refill_caps_at_300(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(
                email="pro@example.com",
                plan="pro",
                subscription_status="active",
                planning_credits=20,
                credits_last_refilled_at=datetime.now(UTC) - timedelta(days=31),
            )
            db.add(user)
            await db.commit()

            await maybe_refill_credits(db, user.id)
            await db.refresh(user)
            assert user.planning_credits == PRO_MAX_CREDITS
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_credits_deduct_after_success_and_transaction_has_balances(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="spend@example.com", planning_credits=20, credits_last_refilled_at=datetime.now(UTC))
            db.add(user)
            await db.commit()

            reservation = await reserve_usage(db, user, FeatureName.WEEKLY_PLANNING)
            await db.refresh(user)
            assert user.planning_credits == 20

            await commit_usage(db, reservation)
            await db.refresh(user)
            assert user.planning_credits == 15

            tx = (
                await db.execute(
                    select(CreditTransaction).where(
                        CreditTransaction.user_id == user.id,
                        CreditTransaction.type == "deduct",
                    )
                )
            ).scalar_one()
            assert tx.amount == -5
            assert tx.balance_before == 20
            assert tx.balance_after == 15
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_failed_operation_does_not_deduct(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="failed@example.com", planning_credits=20, credits_last_refilled_at=datetime.now(UTC))
            db.add(user)
            await db.commit()

            await reserve_usage(db, user, FeatureName.MONTHLY_PLANNING)
            await db.refresh(user)
            assert user.planning_credits == 20
            tx_count = await db.scalar(select(func.count(CreditTransaction.id)).where(CreditTransaction.user_id == user.id))
            assert tx_count == 0
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_insufficient_credits_returns_structured_paywall(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="blocked@example.com", planning_credits=2, credits_last_refilled_at=datetime.now(UTC))
            db.add(user)
            await db.commit()

            with pytest.raises(PaywallError) as exc_info:
                await reserve_usage(db, user, FeatureName.WEEKLY_PLANNING)

            assert exc_info.value.payload["type"] == "paywall"
            assert exc_info.value.payload["reason"] == "NOT_ENOUGH_CREDITS"
            assert exc_info.value.payload["requiredCredits"] == 5
            assert exc_info.value.payload["availableCredits"] == 2
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_admin_grant_and_adjustment_create_transactions(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            admin = User(email="admin@example.com", is_admin=True)
            user = User(email="user@example.com", planning_credits=5)
            db.add_all([admin, user])
            await db.commit()

            await grant_credits(db, user_id=user.id, amount=7, reason="test grant", admin_id=admin.id)
            await adjust_credits(db, user_id=user.id, amount=-3, reason="test adjustment", admin_id=admin.id)
            await db.refresh(user)
            assert user.planning_credits == 9

            txs = (
                await db.execute(
                    select(CreditTransaction)
                    .where(CreditTransaction.user_id == user.id)
                    .order_by(CreditTransaction.created_at)
                )
            ).scalars().all()
            assert [tx.type for tx in txs] == ["admin_grant", "admin_adjustment"]
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_non_admin_cannot_access_admin_dependency():
    async def run():
        user = User(email="not-admin@example.com")
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user)
        assert exc_info.value.status_code == 403

    asyncio.run(run())
