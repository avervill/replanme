"""Bounded LangGraph workflow for proposal-only calendar planning."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.plans import CalendarChangePlan, CalendarChangePlanDraft, DeleteChange


class RouteDecision(BaseModel):
    route: Literal["simple", "weekly_plan", "clarify"] = "simple"
    normalized_request: str = Field(min_length=1, max_length=2000)


class PlannerState(TypedDict, total=False):
    user_id: str
    prompt: str
    timezone: str
    events: list[dict[str, Any]]
    profile: dict[str, Any]
    route: str
    normalized_request: str
    draft: CalendarChangePlanDraft
    plan: CalendarChangePlan
    summary: str
    approved: bool


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )


def _safety_identifier(user_id: str) -> str:
    return hashlib.sha256(f"replanme:{user_id}".encode()).hexdigest()[:64]


async def context_node(state: PlannerState) -> PlannerState:
    return {
        "events": state.get("events", [])[:250],
        "profile": state.get("profile", {}),
    }


async def route_node(state: PlannerState) -> PlannerState:
    response = await _client().responses.parse(
        model=settings.ai_simple_model,
        instructions=(
            "Route a calendar request. Use weekly_plan for multi-day scheduling or workload balancing, "
            "simple for a small explicit change, and clarify only when dates or intent are genuinely missing."
        ),
        input=state["prompt"],
        text_format=RouteDecision,
        max_output_tokens=300,
        reasoning={"effort": "low"},
        store=False,
        safety_identifier=_safety_identifier(state["user_id"]),
    )
    decision = response.output_parsed
    if decision is None:
        raise RuntimeError("Routing model returned no structured output")
    return {"route": decision.route, "normalized_request": decision.normalized_request}


async def plan_node(state: PlannerState) -> PlannerState:
    context = {
        "timezone": state["timezone"],
        "request": state["normalized_request"],
        "current_events": state.get("events", []),
        "planning_profile": state.get("profile", {}),
    }
    response = await _client().responses.parse(
        model=settings.ai_complex_model,
        instructions=(
            "You are Replanme, a cautious calendar planner for students and early-career professionals. "
            "Return only a proposed CalendarChangePlanDraft. Never claim changes were applied. Preserve recovery "
            "time, do not invent event IDs, flag conflicts, minimize destructive edits, and prefer realistic focus "
            "blocks during high-energy windows. A separate endpoint handles approval and execution."
        ),
        input=json.dumps(context, default=str),
        text_format=CalendarChangePlanDraft,
        max_output_tokens=1800,
        reasoning={"effort": "medium"},
        store=False,
        safety_identifier=_safety_identifier(state["user_id"]),
    )
    draft = response.output_parsed
    if draft is None:
        raise RuntimeError("Planning model returned no structured output")
    return {"draft": draft}


async def safety_node(state: PlannerState) -> PlannerState:
    draft = state["draft"]
    warnings = list(draft.warnings)
    if any(isinstance(change, DeleteChange) for change in draft.changes):
        warnings.append("This proposal deletes at least one existing event.")
    if not draft.changes:
        warnings.append("No safe calendar changes were found.")
    draft.warnings = list(dict.fromkeys(warnings))
    return {"draft": draft}


async def approval_node(state: PlannerState) -> PlannerState:
    draft = state["draft"]
    plan = CalendarChangePlan(
        id=uuid.uuid4(),
        summary=draft.summary,
        changes=draft.changes,
        conflicts=draft.conflicts,
        warnings=draft.warnings,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.plan_ttl_seconds),
    )
    return {"plan": plan, "approved": False}


async def execute_node(state: PlannerState) -> PlannerState:
    # Calendar writes intentionally live behind POST /plans/{id}/apply.
    return state


async def summarize_node(state: PlannerState) -> PlannerState:
    plan = state["plan"]
    return {"summary": f"{plan.summary} Review {len(plan.changes)} proposed change(s) before applying."}


def build_planner_graph():
    graph = StateGraph(PlannerState)
    graph.add_node("context", context_node)
    graph.add_node("route", route_node)
    graph.add_node("plan", plan_node)
    graph.add_node("safety", safety_node)
    graph.add_node("approval", approval_node)
    graph.add_node("execute", execute_node)
    graph.add_node("summarize", summarize_node)
    graph.add_edge(START, "context")
    graph.add_edge("context", "route")
    graph.add_edge("route", "plan")
    graph.add_edge("plan", "safety")
    graph.add_edge("safety", "approval")
    graph.add_edge("approval", "execute")
    graph.add_edge("execute", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


planner_graph = build_planner_graph()
