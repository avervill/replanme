import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes.auth import get_google_auth_url
from app.core.config import settings


def test_google_auth_url_requires_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/api/v1/auth/google/callback")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_google_auth_url())

    assert exc_info.value.status_code == 503
    assert "GOOGLE_CLIENT_ID" in exc_info.value.detail


def test_google_auth_url_contains_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/api/v1/auth/google/callback")

    result = asyncio.run(get_google_auth_url())

    assert "client_id=client-id" in result["authorization_url"]
