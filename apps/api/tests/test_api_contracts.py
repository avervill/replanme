from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.routes import imports, voice
from app.core.database import get_db
from app.core.security import get_current_user, get_optional_user
from app.main import app


@pytest.mark.asyncio
async def test_health_contract(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_session_contract_is_anonymous_without_cookie(client):
    app.dependency_overrides[get_optional_user] = lambda: None
    response = await client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


@pytest.mark.asyncio
async def test_calendar_requires_date_range(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    response = await client.get("/api/v1/calendar/events")
    assert response.status_code == 422
    assert {item["loc"][-1] for item in response.json()["detail"]} == {"start", "end"}


@pytest.mark.asyncio
async def test_calendar_rejects_unbounded_window(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    response = await client.get(
        "/api/v1/calendar/events",
        params={"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T00:00:00Z"},
    )
    assert response.status_code == 422
    assert "93 days" in response.json()["detail"]


@pytest.mark.asyncio
async def test_image_import_rejects_unknown_mime(monkeypatch):
    monkeypatch.setattr(imports, "enforce_rate_limit", _noop_rate_limit)
    file = SimpleNamespace(content_type="application/pdf")
    with pytest.raises(Exception) as exc:
        await imports.import_image(
            request=SimpleNamespace(),
            file=file,
            timezone="UTC",
            user=SimpleNamespace(id=uuid.uuid4()),
        )
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_voice_rejects_unknown_mime(monkeypatch):
    monkeypatch.setattr(voice, "enforce_rate_limit", _noop_rate_limit)
    file = SimpleNamespace(content_type="text/plain")
    with pytest.raises(Exception) as exc:
        await voice.transcribe_voice(
            request=SimpleNamespace(),
            file=file,
            user=SimpleNamespace(id=uuid.uuid4()),
        )
    assert exc.value.status_code == 415


async def _noop_rate_limit(*args, **kwargs):
    return None
