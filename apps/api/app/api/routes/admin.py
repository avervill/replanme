"""Authenticated admin controls for analytics, users, and planning credits."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.analytics_event import AnalyticsEvent
from app.models.calendar_connection import CalendarConnection
from app.models.credit_transaction import CreditTransaction
from app.models.planning_request import PlanningRequest
from app.models.user import User
from app.schemas.subscription import AdminCreditChangeRequest, AdminPlanUpdateRequest
from app.services import analytics
from app.services.credits import adjust_credits, grant_credits
from app.services.subscription_service import set_user_plan

router = APIRouter()

SUCCESS_STATUSES = {"success", "applied", "draft_created"}
FAILED_STATUSES = {"failed"}
ACTIVE_EVENT_NAMES = {
    "user_logged_in",
    "ai_prompt_submitted",
    "manual_calendar_event_created",
    "manual_calendar_event_updated",
    "manual_calendar_event_deleted",
    "voice_prompt_used",
    "image_uploaded_to_calendar",
    "planning_applied_to_calendar",
    "planning_draft_created",
}
PAYWALL_EVENT_NAMES = {"paywall_viewed", "paywall_shown"}
GRANT_TRANSACTION_TYPES = {
    "grant",
    "admin_grant",
    "admin_adjustment",
    "signup_bonus",
    "weekly_refill",
    "monthly_pro_refill",
    "subscription_grant",
}


def _is_admin(user: User) -> bool:
    return bool(user.is_admin or user.email.casefold() in settings.admin_email_set)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not _is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _today_start(now: datetime | None = None) -> datetime:
    current = _as_utc(now or datetime.now(UTC))
    return current.replace(hour=0, minute=0, second=0, microsecond=0)


def _range_days(value: str) -> int:
    return 14 if value == "14d" else 30


def _date_key(value: datetime) -> str:
    return _as_utc(value).date().isoformat()


def _empty_series(days: int) -> dict[str, dict[str, int]]:
    start = _today_start() - timedelta(days=days - 1)
    return {
        (start + timedelta(days=index)).date().isoformat(): {
            "signups": 0,
            "planningRequests": 0,
            "creditsUsed": 0,
            "successfulPlanningRequests": 0,
            "failedPlanningRequests": 0,
        }
        for index in range(days)
    }


def _tx_dict(tx: CreditTransaction) -> dict:
    normalized = "adjustment" if tx.type == "admin_adjustment" else "grant" if tx.type == "admin_grant" else tx.type
    return {
        "id": str(tx.id),
        "amount": tx.amount,
        "balanceBefore": tx.balance_before,
        "balanceAfter": tx.balance_after,
        "type": tx.type,
        "normalizedType": normalized,
        "reason": tx.reason,
        "feature": tx.feature,
        "relatedPlanningRequestId": str(tx.related_planning_request_id) if tx.related_planning_request_id else None,
        "createdByAdminId": str(tx.created_by_admin_id) if tx.created_by_admin_id else None,
        "createdAt": tx.created_at.isoformat(),
    }


def _planning_dict(item: PlanningRequest) -> dict:
    return {
        "id": str(item.id),
        "prompt": item.prompt,
        "requestType": item.feature or item.intent or "unknown",
        "intent": item.intent,
        "feature": item.feature,
        "status": item.status,
        "estimatedCredits": item.estimated_credits,
        "creditsUsed": item.credits_used,
        "modelUsed": item.model_used,
        "inputTokens": item.input_tokens,
        "outputTokens": item.output_tokens,
        "totalTokens": item.total_tokens,
        "latencyMs": item.latency_ms,
        "errorMessage": item.error_message,
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }


def _analytics_dict(item: AnalyticsEvent) -> dict:
    return {
        "id": str(item.id),
        "eventName": item.event_name,
        "feature": item.feature,
        "metadata": item.metadata_json,
        "createdAt": item.created_at.isoformat(),
    }


async def _user_stats(db: AsyncSession) -> dict[uuid.UUID, dict[str, int | bool]]:
    planning_rows = await db.execute(
        select(PlanningRequest.user_id, func.count(PlanningRequest.id))
        .where(PlanningRequest.user_id.is_not(None))
        .group_by(PlanningRequest.user_id)
    )
    credit_rows = await db.execute(
        select(CreditTransaction.user_id, func.coalesce(func.sum(-CreditTransaction.amount), 0))
        .where(CreditTransaction.type == "deduct")
        .group_by(CreditTransaction.user_id)
    )
    calendar_rows = await db.execute(select(CalendarConnection.user_id).group_by(CalendarConnection.user_id))
    active_since = datetime.now(UTC) - timedelta(days=7)
    active_rows = await db.execute(
        select(AnalyticsEvent.user_id)
        .where(
            AnalyticsEvent.user_id.is_not(None),
            AnalyticsEvent.event_name.in_(ACTIVE_EVENT_NAMES),
            AnalyticsEvent.created_at >= active_since,
        )
        .group_by(AnalyticsEvent.user_id)
    )
    stats: dict[uuid.UUID, dict[str, int | bool]] = defaultdict(
        lambda: {
            "totalPlanningRequests": 0,
            "totalCreditsUsed": 0,
            "hasGoogleCalendar": False,
            "active": False,
        }
    )
    for user_id, count in planning_rows.all():
        stats[user_id]["totalPlanningRequests"] = int(count or 0)
    for user_id, used in credit_rows.all():
        stats[user_id]["totalCreditsUsed"] = int(used or 0)
    for (user_id,) in calendar_rows.all():
        stats[user_id]["hasGoogleCalendar"] = True
    for (user_id,) in active_rows.all():
        stats[user_id]["active"] = True
    return stats


async def _count_distinct_active_users(db: AsyncSession, since: datetime) -> int:
    return int(
        await db.scalar(
            select(func.count(func.distinct(AnalyticsEvent.user_id))).where(
                AnalyticsEvent.user_id.is_not(None),
                AnalyticsEvent.event_name.in_(ACTIVE_EVENT_NAMES),
                AnalyticsEvent.created_at >= since,
            )
        )
        or 0
    )


@router.get("/analytics/overview")
async def analytics_overview(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    today = _today_start()
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    total_users = int(await db.scalar(select(func.count(User.id))) or 0)
    new_users_today = int(await db.scalar(select(func.count(User.id)).where(User.created_at >= today)) or 0)
    new_users_7d = int(await db.scalar(select(func.count(User.id)).where(User.created_at >= seven_days_ago)) or 0)
    planning_total = int(await db.scalar(select(func.count(PlanningRequest.id))) or 0)
    successful = int(await db.scalar(select(func.count(PlanningRequest.id)).where(PlanningRequest.status.in_(SUCCESS_STATUSES))) or 0)
    failed = int(await db.scalar(select(func.count(PlanningRequest.id)).where(PlanningRequest.status.in_(FAILED_STATUSES))) or 0)
    credits_used = int(
        await db.scalar(
            select(func.coalesce(func.sum(-CreditTransaction.amount), 0)).where(CreditTransaction.type == "deduct")
        )
        or 0
    )
    credits_granted = int(
        await db.scalar(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.amount > 0,
                CreditTransaction.type.in_(GRANT_TRANSACTION_TYPES),
            )
        )
        or 0
    )
    google_connected = int(
        await db.scalar(select(func.count(func.distinct(CalendarConnection.user_id)))) or 0
    )
    paywall_views = int(
        await db.scalar(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.event_name.in_(PAYWALL_EVENT_NAMES))) or 0
    )
    upgrade_clicks = int(
        await db.scalar(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.event_name == "upgrade_clicked")) or 0
    )
    return {
        "totalUsers": total_users,
        "newUsersToday": new_users_today,
        "newUsersLast7Days": new_users_7d,
        "activeUsersToday": await _count_distinct_active_users(db, today),
        "activeUsersLast7Days": await _count_distinct_active_users(db, seven_days_ago),
        "totalPlanningRequests": planning_total,
        "successfulPlanningRequests": successful,
        "failedPlanningRequests": failed,
        "totalCreditsUsed": credits_used,
        "totalCreditsGranted": credits_granted,
        "googleCalendarConnectedUsers": google_connected,
        "paywallViews": paywall_views,
        "upgradeClicks": upgrade_clicks,
    }


@router.get("/analytics/timeseries")
async def analytics_timeseries(
    range: Literal["14d", "30d"] = Query(default="30d"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    days = _range_days(range)
    start = _today_start() - timedelta(days=days - 1)
    series = _empty_series(days)

    users = (await db.execute(select(User).where(User.created_at >= start))).scalars().all()
    for user in users:
        series[_date_key(user.created_at)]["signups"] += 1

    requests = (await db.execute(select(PlanningRequest).where(PlanningRequest.created_at >= start))).scalars().all()
    for request in requests:
        day = _date_key(request.created_at)
        series[day]["planningRequests"] += 1
        if request.status in SUCCESS_STATUSES:
            series[day]["successfulPlanningRequests"] += 1
        if request.status in FAILED_STATUSES:
            series[day]["failedPlanningRequests"] += 1

    transactions = (
        await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.created_at >= start,
                CreditTransaction.type == "deduct",
            )
        )
    ).scalars().all()
    for tx in transactions:
        series[_date_key(tx.created_at)]["creditsUsed"] += max(0, -int(tx.amount))

    return {"range": range, "days": [{"date": date, **values} for date, values in series.items()]}


@router.get("/users")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, alias="pageSize", ge=1, le=100),
    search: str | None = Query(default=None),
    sort: Literal["createdAt", "credits", "email"] = Query(default="createdAt"),
    admin: bool | None = Query(default=None),
    google_connected: bool | None = Query(default=None, alias="googleConnected"),
    active: bool | None = Query(default=None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    users = (await db.execute(select(User))).scalars().all()
    stats = await _user_stats(db)
    normalized_search = search.strip().casefold() if search else None

    rows = []
    for user in users:
        stat = stats[user.id]
        if normalized_search and normalized_search not in user.email.casefold() and normalized_search not in (user.full_name or "").casefold():
            continue
        if admin is not None and bool(user.is_admin) is not admin:
            continue
        if google_connected is not None and bool(stat["hasGoogleCalendar"]) is not google_connected:
            continue
        if active is not None and bool(stat["active"]) is not active:
            continue
        rows.append(
            {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "plan": user.plan,
                "planningCredits": int(user.planning_credits or 0),
                "isAdmin": bool(user.is_admin),
                "subscriptionStatus": user.subscription_status,
                "hasGoogleCalendar": bool(stat["hasGoogleCalendar"]),
                "active": bool(stat["active"]),
                "totalPlanningRequests": int(stat["totalPlanningRequests"]),
                "totalCreditsUsed": int(stat["totalCreditsUsed"]),
                "createdAt": user.created_at.isoformat(),
            }
        )

    if sort == "credits":
        rows.sort(key=lambda item: item["planningCredits"], reverse=True)
    elif sort == "email":
        rows.sort(key=lambda item: item["email"].casefold())
    else:
        rows.sort(key=lambda item: item["createdAt"], reverse=True)

    total = len(rows)
    start = (page - 1) * page_size
    return {"items": rows[start : start + page_size], "total": total, "page": page, "pageSize": page_size}


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user_or_404(db, user_id)
    stats = await _user_stats(db)
    tx_result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(25)
    )
    pr_result = await db.execute(
        select(PlanningRequest)
        .where(PlanningRequest.user_id == user_id)
        .order_by(PlanningRequest.created_at.desc())
        .limit(25)
    )
    analytics_result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user_id)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(50)
    )
    paywall_result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user_id, AnalyticsEvent.event_name.in_(PAYWALL_EVENT_NAMES))
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(25)
    )
    stat = stats[user.id]
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.full_name,
        "plan": user.plan,
        "planningCredits": user.planning_credits,
        "isAdmin": bool(user.is_admin),
        "subscriptionStatus": user.subscription_status,
        "hasGoogleCalendar": bool(stat["hasGoogleCalendar"]),
        "active": bool(stat["active"]),
        "totalPlanningRequests": int(stat["totalPlanningRequests"]),
        "totalCreditsUsed": int(stat["totalCreditsUsed"]),
        "createdAt": user.created_at.isoformat(),
        "creditTransactions": [_tx_dict(tx) for tx in tx_result.scalars()],
        "planningRequests": [_planning_dict(item) for item in pr_result.scalars()],
        "analyticsEvents": [_analytics_dict(item) for item in analytics_result.scalars()],
        "paywallEvents": [_analytics_dict(item) for item in paywall_result.scalars()],
    }


@router.get("/users/{user_id}/credit-transactions")
async def get_credit_transactions(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_user_or_404(db, user_id)
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
    )
    return [_tx_dict(tx) for tx in result.scalars()]


@router.get("/users/{user_id}/planning-requests")
async def get_planning_requests(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_user_or_404(db, user_id)
    result = await db.execute(
        select(PlanningRequest)
        .where(PlanningRequest.user_id == user_id)
        .order_by(PlanningRequest.created_at.desc())
    )
    return [_planning_dict(item) for item in result.scalars()]


@router.post("/users/{user_id}/credits/grant")
async def grant_user_credits(
    user_id: uuid.UUID,
    payload: AdminCreditChangeRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_user_or_404(db, user_id)
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Grant amount must be positive.")
    try:
        balance = await grant_credits(
            db,
            user_id=user_id,
            amount=payload.amount,
            reason=payload.reason,
            admin_id=admin.id,
            transaction_type="grant",
        )
        await analytics.track_event(db, user_id, "credits_granted", {"amount": payload.amount, "adminId": str(admin.id)})
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"ok": True, "userId": str(user_id), "planningCredits": balance}


@router.post("/users/{user_id}/credits/adjust")
async def adjust_user_credits(
    user_id: uuid.UUID,
    payload: AdminCreditChangeRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_user_or_404(db, user_id)
    try:
        balance = await adjust_credits(
            db,
            user_id=user_id,
            amount=payload.amount,
            reason=payload.reason,
            admin_id=admin.id,
        )
        await analytics.track_event(db, user_id, "credits_granted", {"amount": payload.amount, "adminId": str(admin.id)})
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"ok": True, "userId": str(user_id), "planningCredits": balance}


@router.post("/users/{user_id}/plan")
async def update_user_plan(
    user_id: uuid.UUID,
    payload: AdminPlanUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | bool]:
    try:
        user = await set_user_plan(db, user_id, payload.plan, admin.id)
        if payload.subscriptionStatus:
            user.subscription_status = "none" if payload.subscriptionStatus == "inactive" else payload.subscriptionStatus
        db.add(user)
        await analytics.track_event(db, user_id, "credits_refilled", {"source": "plan_change", "adminId": str(admin.id)})
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True, "userId": str(user.id), "plan": user.plan, "subscriptionStatus": user.subscription_status}
