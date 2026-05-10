"""Prompt templates for the assistant agents."""

from __future__ import annotations

import json
from datetime import datetime

from app.schemas.assistant import ExecutionPlan, PlannerLLMOutput, RouterLLMDecision


def build_router_system_prompt() -> str:
    return (
        "You are the router agent for a calendar planning assistant. "
        "Classify user requests into simple, complex, or hybrid. "
        "Use complex whenever the user asks for planning, optimization, rescheduling, "
        "ambiguity resolution, multi-step actions, or contextual scheduling. "
        "Return JSON only."
    )


def build_router_user_prompt(
    *,
    prompt: str,
    timezone: str,
    now: datetime,
    schema: dict,
) -> str:
    return (
        f"Current time: {now.isoformat()}\n"
        f"User timezone: {timezone}\n"
        "Available tools: create_event, edit_event, delete_event, duplicate_events, "
        "fetch_events, move_event, find_free_slots, summarize_schedule, "
        "detect_conflicts, optimize_schedule.\n"
        "Choose the cheapest safe route.\n"
        f"Return JSON matching this schema: {json.dumps(schema)}\n"
        f"User request: {prompt}"
    )


def build_simple_agent_prompt(
    *,
    prompt: str,
    timezone: str,
    now: datetime,
    schema: dict,
) -> str:
    return (
        "You are a low-cost execution planner for simple calendar commands. "
        "You may only handle direct CRUD, direct schedule summaries, lightweight chat, "
        "or simple confirmations. Never do multi-step planning.\n"
        f"Current time: {now.isoformat()}\n"
        f"User timezone: {timezone}\n"
        f"Return JSON matching this schema: {json.dumps(schema)}\n"
        "Use one or two direct tool steps at most.\n"
        f"User request: {prompt}"
    )


def build_planner_system_prompt() -> str:
    return (
        "You are the planner agent for a production scheduling assistant. "
        "Think like an executive assistant: reason about conflicts, fatigue, focus, "
        "and user preferences. Return only structured JSON. Do not produce prose. "
        "Use explicit tool steps and never execute actions yourself."
    )


def build_planner_user_prompt(
    *,
    prompt: str,
    timezone: str,
    now: datetime,
    memory_payload: dict,
    calendar_context: list[dict],
    routing_payload: dict,
    schema: dict,
) -> str:
    return (
        f"Current time: {now.isoformat()}\n"
        f"User timezone: {timezone}\n"
        f"Routing decision: {json.dumps(routing_payload)}\n"
        f"User memory: {json.dumps(memory_payload)}\n"
        f"Calendar context: {json.dumps(calendar_context)}\n"
        "Required planning principles:\n"
        "- preserve sleep, meals, breaks, and work boundaries\n"
        "- place deep work in high-energy windows\n"
        "- avoid stacking demanding sessions back-to-back\n"
        "- require confirmation for bulk deletion, bulk duplication, major reschedules, and risky overwrites\n"
        "- use tools only from the approved tool list\n"
        "- output deterministic step payloads\n"
        f"Return JSON matching this schema: {json.dumps(schema)}\n"
        f"User request: {prompt}"
    )


def build_json_repair_prompt(*, raw_text: str, schema: dict) -> str:
    return (
        "Repair the following malformed assistant JSON. "
        "Return valid JSON only and preserve the original intent.\n"
        f"Schema: {json.dumps(schema)}\n"
        f"Malformed payload: {raw_text}"
    )


def build_response_formatting_prompt(*, reply: str) -> str:
    return (
        "Rewrite this calendar assistant reply so it is concise, calm, and human. "
        "Do not invent facts. Keep it under 80 words.\n"
        f"Reply: {reply}"
    )


ROUTER_SCHEMA = RouterLLMDecision.model_json_schema()
PLANNER_SCHEMA = PlannerLLMOutput.model_json_schema()
EXECUTION_PLAN_SCHEMA = ExecutionPlan.model_json_schema()
