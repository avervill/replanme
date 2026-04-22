"""Google Calendar API v3 wrapper using httpx."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_token, encrypt_token
from app.core.config import settings
from app.models.calendar_connection import CalendarConnection

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

async def exchange_google_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_google_token(refresh_token: str) -> dict:
    """Use a refresh token to obtain a new access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_google_userinfo(access_token: str) -> dict:
    """Fetch basic profile info from Google."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Ensure valid access token (auto-refresh if expired)
# ---------------------------------------------------------------------------

async def _ensure_valid_token(
    conn: CalendarConnection, db: AsyncSession
) -> str:
    """Return a valid Google access token, refreshing if expired."""
    if conn.access_token is None:
        raise ValueError("No access token stored for this connection")

    access = decrypt_token(conn.access_token)

    if conn.token_expires_at and conn.token_expires_at < datetime.now(UTC):
        if conn.refresh_token is None:
            raise ValueError("Token expired and no refresh token available")
        logger.info("Refreshing expired Google token for user %s", conn.user_id)
        token_data = await refresh_google_token(decrypt_token(conn.refresh_token))
        access = token_data["access_token"]
        conn.access_token = encrypt_token(access)
        conn.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=token_data.get("expires_in", 3600)
        )
        db.add(conn)
        await db.commit()
        await db.refresh(conn)

    return access


async def _get_connection(
    user_id, db: AsyncSession
) -> CalendarConnection:
    result = await db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == user_id,
            CalendarConnection.provider == "google",
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise ValueError("No Google Calendar connection found")
    return conn


# ---------------------------------------------------------------------------
# Calendar CRUD operations
# ---------------------------------------------------------------------------

async def list_google_events(
    user_id, db: AsyncSession, *, max_results: int = 250
) -> list[dict]:
    """List upcoming events from the user's primary Google Calendar."""
    conn = await _get_connection(user_id, db)
    access = await _ensure_valid_token(conn, db)
    now = datetime.now(UTC)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GOOGLE_CALENDAR_BASE}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access}"},
            params={
                "maxResults": max_results,
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": (now - timedelta(days=90)).isoformat(),
                "timeMax": (now + timedelta(days=365)).isoformat(),
            },
        )
        resp.raise_for_status()
        return resp.json().get("items", [])


async def create_google_event(
    user_id, db: AsyncSession, *, event_body: dict
) -> dict:
    """Create an event on the user's primary Google Calendar."""
    conn = await _get_connection(user_id, db)
    access = await _ensure_valid_token(conn, db)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GOOGLE_CALENDAR_BASE}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access}"},
            json=event_body,
        )
        resp.raise_for_status()
        return resp.json()


async def update_google_event(
    user_id, db: AsyncSession, *, event_id: str, event_body: dict
) -> dict:
    """Update an existing event on the user's primary Google Calendar."""
    conn = await _get_connection(user_id, db)
    access = await _ensure_valid_token(conn, db)

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{GOOGLE_CALENDAR_BASE}/calendars/primary/events/{event_id}",
            headers={"Authorization": f"Bearer {access}"},
            json=event_body,
        )
        resp.raise_for_status()
        return resp.json()


async def delete_google_event(
    user_id, db: AsyncSession, *, event_id: str
) -> None:
    """Delete an event from the user's primary Google Calendar."""
    conn = await _get_connection(user_id, db)
    access = await _ensure_valid_token(conn, db)

    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GOOGLE_CALENDAR_BASE}/calendars/primary/events/{event_id}",
            headers={"Authorization": f"Bearer {access}"},
        )
        resp.raise_for_status()
