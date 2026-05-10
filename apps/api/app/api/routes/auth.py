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
from app.services import analytics
from app.services.credits import grant_signup_credits_if_needed, maybe_refill_credits
from app.services.google_calendar import exchange_google_code, get_google_userinfo
from app.services.paywall import normalize_subscription_status

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
        user.is_admin = email.casefold() in settings.admin_email_set
        db.add(user)
        await db.flush()
        await grant_signup_credits_if_needed(db, user)
        await analytics.track_event(db, user.id, "user_signed_up", {"provider": "google"})
        logger.info("Created new user %s (%s)", user.id, email)
    else:
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        user.is_admin = user.is_admin or email.casefold() in settings.admin_email_set
        db.add(user)
        await grant_signup_credits_if_needed(db, user)
        await maybe_refill_credits(db, user.id)
        await analytics.track_event(db, user.id, "user_logged_in", {"provider": "google"})

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
        await analytics.track_event(db, user.id, "google_calendar_connected", {"provider": "google"})
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
    user.is_admin = user.is_admin or user.email.casefold() in settings.admin_email_set
    await grant_signup_credits_if_needed(db, user)
    await maybe_refill_credits(db, user.id)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        timezone=user.timezone,
        has_google_calendar=has_calendar,
        plan=user.plan or "free",
        subscription_status=normalize_subscription_status(user.subscription_status),
        planning_credits=int(user.planning_credits or 0),
        is_admin=bool(user.is_admin),
    )


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    """Logout placeholder — with JWTs, the client simply discards the token.
    A future improvement can add token blacklisting via Redis."""
    return {"detail": "Logged out successfully"}
