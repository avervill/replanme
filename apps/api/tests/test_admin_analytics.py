import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.admin import analytics_overview, analytics_timeseries, list_users, require_admin
from app.models import Base
from app.models.analytics_event import AnalyticsEvent
from app.models.calendar_connection import CalendarConnection
from app.models.credit_transaction import CreditTransaction
from app.models.planning_request import PlanningRequest
from app.models.user import User
from app.services import analytics


async def _session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin_analytics.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory()


def test_admin_dependency_allows_only_admins():
    async def run():
        admin = User(email="admin@example.com", is_admin=True)
        normal = User(email="normal@example.com")

        assert await require_admin(admin) is admin
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(normal)
        assert exc_info.value.status_code == 403

    asyncio.run(run())


def test_admin_overview_and_timeseries_counts_seeded_data(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            now = datetime.now(UTC)
            admin = User(email="admin@example.com", is_admin=True, planning_credits=10)
            user = User(email="user@example.com", planning_credits=5)
            db.add_all([admin, user])
            await db.flush()
            db.add(
                CalendarConnection(
                    user_id=user.id,
                    provider="google",
                    external_email=user.email,
                    status="active",
                    scopes="calendar",
                )
            )
            db.add_all(
                [
                    PlanningRequest(user_id=user.id, intent="quick_add", status="applied", credits_used=1),
                    PlanningRequest(user_id=user.id, intent="complex_plan", status="failed", credits_used=0),
                    CreditTransaction(
                        user_id=user.id,
                        amount=-1,
                        balance_before=5,
                        balance_after=4,
                        type="deduct",
                        reason="test spend",
                    ),
                    CreditTransaction(
                        user_id=user.id,
                        amount=10,
                        balance_before=4,
                        balance_after=14,
                        type="grant",
                        reason="test grant",
                        created_by_admin_id=admin.id,
                    ),
                    AnalyticsEvent(user_id=user.id, event_name="user_logged_in", created_at=now),
                    AnalyticsEvent(user_id=user.id, event_name="paywall_viewed", created_at=now),
                    AnalyticsEvent(user_id=user.id, event_name="upgrade_clicked", created_at=now),
                ]
            )
            await db.commit()

            overview = await analytics_overview(admin, db)
            assert overview["totalUsers"] == 2
            assert overview["totalPlanningRequests"] == 2
            assert overview["successfulPlanningRequests"] == 1
            assert overview["failedPlanningRequests"] == 1
            assert overview["totalCreditsUsed"] == 1
            assert overview["totalCreditsGranted"] == 10
            assert overview["googleCalendarConnectedUsers"] == 1
            assert overview["paywallViews"] == 1
            assert overview["upgradeClicks"] == 1

            series = await analytics_timeseries("14d", admin, db)
            today = now.date().isoformat()
            today_row = next(row for row in series["days"] if row["date"] == today)
            assert today_row["planningRequests"] == 2
            assert today_row["creditsUsed"] == 1
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_admin_users_supports_search_filter_and_pagination(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            admin = User(email="admin@example.com", full_name="Admin", is_admin=True)
            alpha = User(email="alpha@example.com", full_name="Alpha User", planning_credits=2)
            beta = User(email="beta@example.com", full_name="Beta User", planning_credits=20)
            db.add_all([admin, alpha, beta])
            await db.flush()
            await analytics.track_event(db, alpha.id, "user_logged_in", {"test": True})
            await db.commit()

            searched = await list_users(
                page=1,
                page_size=10,
                search="alpha",
                sort="email",
                admin=None,
                google_connected=None,
                active=None,
                _=admin,
                db=db,
            )
            assert searched["total"] == 1
            assert searched["items"][0]["email"] == "alpha@example.com"

            active = await list_users(
                page=1,
                page_size=10,
                search=None,
                sort="createdAt",
                admin=None,
                google_connected=None,
                active=True,
                _=admin,
                db=db,
            )
            assert active["total"] == 1
            assert active["items"][0]["email"] == "alpha@example.com"
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_planning_request_logging_and_status_update(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="plan@example.com")
            db.add(user)
            await db.flush()
            request = await analytics.log_planning_request(
                db,
                user_id=user.id,
                request_type="complex_plan",
                prompt="plan my day",
                estimated_credits=3,
            )
            await analytics.update_planning_request_status(
                db,
                request,
                "draft_created",
                credits_used=3,
                latency_ms=125,
            )
            await db.commit()

            assert request.intent == "complex_plan"
            assert request.status == "draft_created"
            assert request.credits_used == 3
            assert request.latency_ms == 125
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
