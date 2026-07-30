"""Opaque sessions and dedicated token encryption."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis


def _session_key(token: str) -> str:
    return f"session:{hashlib.sha256(token.encode()).hexdigest()}"


async def create_session(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.set(
        _session_key(token),
        json.dumps({"user_id": str(user_id), "created_at": datetime.now(UTC).isoformat()}),
        ex=settings.session_ttl_seconds,
    )
    return token


async def revoke_session(token: str | None) -> None:
    if token:
        redis = await get_redis()
        await redis.delete(_session_key(token))


async def session_user_id(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    redis = await get_redis()
    raw = await redis.get(_session_key(token))
    if not raw:
        return None
    try:
        return uuid.UUID(json.loads(raw)["user_id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User

    user_id = await session_user_id(request.cookies.get(settings.session_cookie_name))
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(user=Depends(get_optional_user)):
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return user


def _fernet() -> Fernet:
    if not settings.token_encryption_key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required for Google token storage")
    return Fernet(settings.token_encryption_key.encode())


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_token(cipher: str) -> str:
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Stored Google token could not be decrypted") from exc
