"""Authenticated admin controls for plans and planning credits."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.calendar_connection import CalendarConnection
from app.models.analytics_event import AnalyticsEvent
from app.models.credit_transaction import CreditTransaction
from app.models.planning_request import PlanningRequest
from app.models.user import User
from app.schemas.subscription import AdminCreditChangeRequest, AdminPlanUpdateRequest
from app.services import analytics
from app.services.credits import adjust_credits, grant_credits
from app.services.subscription_service import set_user_plan

router = APIRouter()


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


def _tx_dict(tx: CreditTransaction) -> dict:
    return {
        "id": str(tx.id),
        "amount": tx.amount,
        "balanceBefore": tx.balance_before,
        "balanceAfter": tx.balance_after,
        "type": tx.type,
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
        "intent": item.intent,
        "feature": item.feature,
        "status": item.status,
        "estimatedCredits": item.estimated_credits,
        "creditsUsed": item.credits_used,
        "modelUsed": item.model_used,
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


@router.get("/users")
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    rows = []
    for user in result.scalars():
        planning_count = await db.scalar(select(func.count(PlanningRequest.id)).where(PlanningRequest.user_id == user.id))
        credits_used = await db.scalar(
            select(func.coalesce(func.sum(-CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.type == "deduct",
            )
        )
        calendar_count = await db.scalar(select(func.count(CalendarConnection.id)).where(CalendarConnection.user_id == user.id))
        rows.append(
            {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "plan": user.plan,
                "planningCredits": user.planning_credits,
                "isAdmin": bool(user.is_admin),
                "subscriptionStatus": user.subscription_status,
                "hasGoogleCalendar": bool(calendar_count),
                "totalPlanningRequests": int(planning_count or 0),
                "totalCreditsUsed": int(credits_used or 0),
                "createdAt": user.created_at.isoformat(),
            }
        )
    return rows


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user_or_404(db, user_id)
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
    event_result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user_id, AnalyticsEvent.event_name == "paywall_shown")
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(25)
    )
    conn_result = await db.execute(select(CalendarConnection.id).where(CalendarConnection.user_id == user_id))
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.full_name,
        "plan": user.plan,
        "planningCredits": user.planning_credits,
        "isAdmin": bool(user.is_admin),
        "subscriptionStatus": user.subscription_status,
        "hasGoogleCalendar": conn_result.scalar_one_or_none() is not None,
        "createdAt": user.created_at.isoformat(),
        "creditTransactions": [_tx_dict(tx) for tx in tx_result.scalars()],
        "planningRequests": [_planning_dict(item) for item in pr_result.scalars()],
        "paywallEvents": [_analytics_dict(item) for item in event_result.scalars()],
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
