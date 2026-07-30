"""Google OAuth with PKCE and opaque, revocable browser sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_session, encrypt_token, get_optional_user, revoke_session
from app.models.calendar_connection import GoogleConnection
from app.models.user import User
from app.schemas.auth import SessionResponse, UserResponse
from app.services.google_calendar import exchange_google_code, get_google_userinfo

logger = logging.getLogger(__name__)
router = APIRouter()
OAUTH_STATE_TTL_SECONDS = 600
GOOGLE_SCOPES = "openid email profile https://www.googleapis.com/auth/calendar"


def _oauth_configured() -> bool:
    return bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_uri
        and settings.google_allowed_email_set
    )


@router.get("/google/start")
async def google_start() -> RedirectResponse:
    if not _oauth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth or GOOGLE_ALLOWED_EMAILS is not configured",
        )
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redis = await get_redis()
    await redis.set(f"oauth:state:{state}", json.dumps({"verifier": verifier}), ex=OAUTH_STATE_TTL_SECONDS)

    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=302)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    redis = await get_redis()
    key = f"oauth:state:{state}"
    raw = await redis.getdel(key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state is invalid or expired")
    verifier = json.loads(raw).get("verifier")
    if not verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state is malformed")

    try:
        token_data = await exchange_google_code(code, code_verifier=verifier)
        userinfo = await get_google_userinfo(token_data["access_token"])
    except Exception as exc:
        logger.warning("Google OAuth exchange failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google sign-in failed") from exc

    email = str(userinfo.get("email", "")).casefold()
    if email not in settings.google_allowed_email_set:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This Google account is not on the test-user allowlist"
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=userinfo.get("name"))
        db.add(user)
        await db.flush()
    elif userinfo.get("name"):
        user.full_name = userinfo["name"]

    result = await db.execute(select(GoogleConnection).where(GoogleConnection.user_id == user.id))
    connection = result.scalar_one_or_none()
    access = encrypt_token(token_data["access_token"])
    refresh = token_data.get("refresh_token")
    expiry = datetime.now(UTC) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    if connection is None:
        connection = GoogleConnection(
            user_id=user.id,
            external_email=email,
            scopes=GOOGLE_SCOPES,
            access_token_encrypted=access,
            refresh_token_encrypted=encrypt_token(refresh) if refresh else None,
            token_expires_at=expiry,
        )
    else:
        connection.access_token_encrypted = access
        connection.refresh_token_encrypted = encrypt_token(refresh) if refresh else connection.refresh_token_encrypted
        connection.token_expires_at = expiry
        connection.status = "active"
    db.add(connection)
    await db.commit()

    session_token = await create_session(user.id)
    response = RedirectResponse(f"{settings.frontend_url}/dashboard", status_code=303)
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure or settings.is_production,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/session", response_model=SessionResponse)
async def session(
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    if user is None:
        return SessionResponse(authenticated=False)
    result = await db.execute(
        select(GoogleConnection.id).where(GoogleConnection.user_id == user.id, GoogleConnection.status == "active")
    )
    return SessionResponse(
        authenticated=True,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            timezone=user.timezone,
            has_google_calendar=result.scalar_one_or_none() is not None,
        ),
    )


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    await revoke_session(request.cookies.get(settings.session_cookie_name))
    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
