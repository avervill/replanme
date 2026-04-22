"""Authentication routes – Google OAuth2 flow + JWT issuance."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, encrypt_token, get_current_user
from app.models.calendar_connection import CalendarConnection
from app.models.user import User
from app.schemas.auth import TokenResponse, UserResponse
from app.services.google_calendar import exchange_google_code, get_google_userinfo

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Step 1 — Redirect user to Google consent screen
# ---------------------------------------------------------------------------

@router.get("/google/url")
async def get_google_auth_url() -> dict[str, str]:
    if settings.missing_google_oauth_settings:
        missing = ", ".join(settings.missing_google_oauth_settings)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google OAuth is not configured. Missing: {missing}",
        )

    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile https://www.googleapis.com/auth/calendar",
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return {
        "provider": "google",
        "authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
    }


# ---------------------------------------------------------------------------
# Step 2 — Google redirects back with ?code=...
# ---------------------------------------------------------------------------

@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Exchange the Google authorization code for tokens, create or update the
    user, store encrypted tokens, and redirect to the frontend with a JWT."""

    if settings.missing_google_oauth_settings:
        missing = ", ".join(settings.missing_google_oauth_settings)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google OAuth is not configured. Missing: {missing}",
        )

    # 1. Exchange code for tokens
    try:
        token_data = await exchange_google_code(code)
    except Exception as exc:
        logger.error("Google token exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code",
        ) from exc

    access_token_google = token_data["access_token"]
    refresh_token_google = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    # 2. Fetch user profile
    try:
        userinfo = await get_google_userinfo(access_token_google)
    except Exception as exc:
        logger.error("Google userinfo fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch user info from Google",
        ) from exc

    email = userinfo["email"]
    full_name = userinfo.get("name")

    # 3. Upsert user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, full_name=full_name)
        db.add(user)
        await db.flush()
        logger.info("Created new user %s (%s)", user.id, email)
    else:
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            db.add(user)

    # 4. Upsert calendar connection with encrypted tokens
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == user.id,
            CalendarConnection.provider == "google",
        )
    )
    conn = result.scalar_one_or_none()

    encrypted_access = encrypt_token(access_token_google)
    encrypted_refresh = encrypt_token(refresh_token_google) if refresh_token_google else None
    token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

    if conn is None:
        conn = CalendarConnection(
            user_id=user.id,
            provider="google",
            external_email=email,
            status="active",
            scopes="openid email profile https://www.googleapis.com/auth/calendar",
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expires_at=token_expiry,
        )
        db.add(conn)
    else:
        conn.access_token = encrypted_access
        if encrypted_refresh:
            conn.refresh_token = encrypted_refresh
        conn.token_expires_at = token_expiry
        conn.status = "active"
        db.add(conn)

    await db.commit()

    # 5. Issue JWT
    jwt_token = create_access_token(user.id)

    # 6. Redirect to frontend with the token
    redirect_url = f"{settings.frontend_url}/auth/callback?token={jwt_token}"
    return RedirectResponse(url=redirect_url)


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Return the authenticated user's profile."""
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == user.id,
            CalendarConnection.provider == "google",
        )
    )
    has_calendar = result.scalar_one_or_none() is not None

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        timezone=user.timezone,
        has_google_calendar=has_calendar,
    )


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    """Logout placeholder — with JWTs, the client simply discards the token.
    A future improvement can add token blacklisting via Redis."""
    return {"detail": "Logged out successfully"}
