import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.onboarding import complete_onboarding, onboarding_status, save_onboarding, skip_onboarding
from app.core.security import get_current_user
from app.models import Base
from app.models.user import User
from app.schemas.onboarding import OnboardingSaveRequest


async def _session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'onboarding.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory()


def _payload() -> OnboardingSaveRequest:
    return OnboardingSaveRequest(
        role="Developer",
        mainGoal="Weekly life organization",
        planningPain="I overpack my schedule",
        energyProfile={
            "peakFocusTime": "Morning",
            "lowEnergyTime": "Evening",
            "preferredWorkBlockLength": "60 minutes",
            "sleepPreference": "I need 8+ hours of sleep",
        },
        calendarIntent="Use my calendar to avoid conflicts",
        firstPrompt="Plan my week around deep work and recovery.",
    )


def test_new_user_onboarding_status_is_incomplete(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="new@example.com")
            db.add(user)
            await db.commit()

            status = await onboarding_status(user)

            assert status.onboardingCompleted is False
            assert status.onboardingSkipped is False
            assert status.onboardingData is None
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_save_onboarding_persists_data(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="save@example.com")
            db.add(user)
            await db.flush()

            status = await save_onboarding(_payload(), user, db)

            assert status.onboardingCompleted is False
            assert status.onboardingData is not None
            assert status.onboardingData["role"] == "Developer"
            assert status.onboardingData["energyProfile"]["peakFocusTime"] == "Morning"
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_save_onboarding_accepts_multiple_choice_data(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="multi@example.com")
            db.add(user)
            await db.flush()

            payload = OnboardingSaveRequest(
                role="Student",
                mainGoal=["Study / exam planning", "Fitness and habits"],
                planningPain=["I procrastinate", "My calendar is messy"],
                energyProfile={
                    "peakFocusTime": ["Morning", "Evening"],
                    "lowEnergyTime": ["Afternoon"],
                    "preferredWorkBlockLength": ["45 minutes", "60 minutes"],
                    "sleepPreference": ["I need 8+ hours of sleep"],
                },
                calendarIntent="Use my calendar to avoid conflicts",
                firstPrompt="Plan a balanced week.",
            )
            status = await save_onboarding(payload, user, db)

            assert status.onboardingData is not None
            assert status.onboardingData["mainGoal"] == ["Study / exam planning", "Fitness and habits"]
            assert status.onboardingData["energyProfile"]["peakFocusTime"] == ["Morning", "Evening"]
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_complete_onboarding_updates_only_current_user(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            current = User(email="current@example.com")
            other = User(email="other@example.com")
            db.add_all([current, other])
            await db.flush()

            status = await complete_onboarding(current, db)
            await db.refresh(other)

            assert status.onboardingCompleted is True
            assert current.onboarding_completed_at is not None
            assert other.onboarding_completed is False
            assert other.onboarding_completed_at is None
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_skip_onboarding_marks_completed(tmp_path):
    async def run():
        engine, db = await _session(tmp_path)
        try:
            user = User(email="skip@example.com")
            db.add(user)
            await db.flush()

            status = await skip_onboarding(user, db)

            assert status.onboardingCompleted is True
            assert status.onboardingSkipped is True
            assert user.onboarding_completed_at is not None
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_onboarding_auth_dependency_rejects_unauthorized():
    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None, db=None)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 401

    asyncio.run(run())


def test_onboarding_endpoint_rejects_unauthorized():
    from app.api.routes.onboarding import router

    app = FastAPI()
    app.include_router(router, prefix="/onboarding")
    client = TestClient(app)

    response = client.get("/onboarding/status")

    assert response.status_code == 401
