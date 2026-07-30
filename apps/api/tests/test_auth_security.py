from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from cryptography.fernet import Fernet

from app.api.routes import auth
from app.core import security
from app.core.config import settings


@pytest.mark.asyncio
async def test_google_start_uses_state_and_pkce(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "google_client_id", "client")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_allowed_emails", "student@example.com")
    monkeypatch.setattr(auth, "get_redis", lambda: _async_value(fake_redis))

    response = await auth.google_start()
    assert response.status_code == 302
    location = response.headers["location"]
    assert "code_challenge_method=S256" in location
    assert "state=" in location
    stored = next(iter(fake_redis.values.values()))
    assert len(json.loads(stored)["verifier"]) > 40


def test_google_tokens_use_dedicated_fernet_key(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    encrypted = security.encrypt_token("google-token")
    assert encrypted != "google-token"
    assert security.decrypt_token(encrypted) == "google-token"


@pytest.mark.asyncio
async def test_opaque_session_is_hashed_in_redis(monkeypatch, fake_redis):
    monkeypatch.setattr(security, "get_redis", lambda: _async_value(fake_redis))
    user_id = uuid.uuid4()
    token = await security.create_session(user_id)
    assert token not in " ".join(fake_redis.values.keys())
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert f"session:{digest}" in fake_redis.values
    assert await security.session_user_id(token) == user_id
    await security.revoke_session(token)
    assert await security.session_user_id(token) is None


async def _async_value(value):
    return value
