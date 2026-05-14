"""Intent classification before any calendar mutation."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.llm.gemma import GemmaClient
from app.services.assistant.types import IntentClassification, PlanningState

REVISION_PHRASES = (
    "add more",
    "not enough",
    "make it more intense",
    "hours is little",
    "hour is little",
    "too little",
    "use other days",
    "plan more preparation",
    "make it better",
    "too short",
    "more study time",
    "very more hours",
)
CONFIRM_PHRASES = ("yes", "add it", "schedule it", "put it in calendar", "confirm", "looks good", "apply")
REJECT_PHRASES = ("no", "cancel", "don't add", "do not add", "reject", "stop")


def deterministic_intent(prompt: str, planning_state: PlanningState | None = None) -> IntentClassification | None:
    normalized = " ".join(prompt.casefold().split())
    has_plan = bool(planning_state and planning_state.latest_plan)

    if has_plan and any(phrase in normalized for phrase in CONFIRM_PHRASES):
        return IntentClassification(
            intent="confirm_plan_to_calendar",
            confidence=0.96,
            is_calendar_mutation=True,
            requires_planning=False,
            requires_calendar_read=False,
            requires_user_confirmation=False,
            complexity_hint="low",
            reason="User confirmed the active generated plan.",
        )
    active_plan = bool(planning_state and planning_state.active and planning_state.latest_plan)
    if active_plan and any(phrase in normalized for phrase in REJECT_PHRASES):
        return IntentClassification(
            intent="reject_plan",
            confidence=0.94,
            reason="User rejected the active generated plan.",
        )
    if active_plan and any(phrase in normalized for phrase in REVISION_PHRASES):
        return IntentClassification(
            intent="modify_existing_plan",
            confidence=0.95,
            requires_planning=True,
            requires_calendar_read=True,
            requires_user_confirmation=True,
            complexity_hint="medium",
            reason="User asks to revise the active generated plan.",
        )

    if any(phrase in normalized for phrase in ("optimize", "rebuild my schedule", "rebuild schedule", "full week rebuild")):
        return IntentClassification(
            intent="optimize_schedule",
            confidence=0.9,
            requires_planning=True,
            requires_calendar_read=True,
            requires_user_confirmation=True,
            complexity_hint="high",
            reason="User asked for schedule optimization or rebuild.",
        )

    planning_terms = (
        "plan my",
        "plan preparing",
        "prepare for",
        "study plan",
        "final",
        "exam",
        "deadline",
        "whole week",
        "my week",
        "this week",
        "month",
    )
    if any(term in normalized for term in planning_terms) and any(
        verb in normalized for verb in ("plan", "prepare", "organize", "build", "schedule")
    ):
        return IntentClassification(
            intent="generate_plan",
            confidence=0.9,
            requires_planning=True,
            requires_calendar_read=True,
            requires_user_confirmation=True,
            complexity_hint="medium" if "week" not in normalized else "high",
            planning_scope="whole_week" if "week" in normalized else "whole_month" if "month" in normalized else "custom",
            reason="User asked for a generated multi-step plan.",
        )

    if re.search(r"\b(add|create|schedule|book|set up|put|make)\b", normalized):
        return IntentClassification(
            intent="create_single_event",
            confidence=0.85,
            is_calendar_mutation=True,
            requires_planning=False,
            requires_calendar_read=True,
            requires_user_confirmation=False,
            complexity_hint="low",
            reason="User appears to request one direct calendar event.",
        )

    if any(word in normalized for word in ("delete", "remove", "clear")):
        return IntentClassification(
            intent="delete_event",
            confidence=0.85,
            is_calendar_mutation=True,
            requires_calendar_read=True,
            requires_user_confirmation=True,
            reason="User asks to delete calendar events.",
        )
    if any(word in normalized for word in ("move", "reschedule", "later", "earlier")):
        return IntentClassification(
            intent="move_event",
            confidence=0.8,
            is_calendar_mutation=True,
            requires_calendar_read=True,
            requires_user_confirmation=True,
            reason="User asks to move or reschedule an event.",
        )
    if any(word in normalized for word in ("duplicate", "copy")):
        return IntentClassification(
            intent="duplicate_period" if any(word in normalized for word in ("week", "day", "period")) else "duplicate_event",
            confidence=0.82,
            is_calendar_mutation=True,
            requires_calendar_read=True,
            requires_user_confirmation=True,
            reason="User asks to duplicate calendar material.",
        )
    if re.search(r"\b(what|show|list|find|when)\b", normalized):
        return IntentClassification(
            intent="answer_question",
            confidence=0.75,
            requires_calendar_read=any(word in normalized for word in ("calendar", "schedule", "event", "today", "tomorrow", "week")),
            reason="User asks a question.",
        )
    return None


class IntentClassifier:
    def __init__(self, client: object | None = None, gemma_client: GemmaClient | None = None):
        self.gemma = gemma_client or GemmaClient()

    async def classify(
        self,
        *,
        prompt: str,
        planning_state: PlanningState | None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> IntentClassification:
        deterministic = deterministic_intent(prompt, planning_state)

        gemma_payload = {
            "message": prompt,
            "has_active_plan": bool(planning_state and planning_state.active and planning_state.latest_plan),
            "active_plan_summary": planning_state.latest_assistant_plan_summary if planning_state else "",
            "attachments_count": len(attachments or []),
            "deterministic_baseline": deterministic.model_dump(mode="json") if deterministic else None,
            "allowed_intents": [
                "simple_chat",
                "create_single_event",
                "delete_event",
                "update_event",
                "move_event",
                "duplicate_event",
                "duplicate_period",
                "generate_plan",
                "modify_existing_plan",
                "optimize_schedule",
                "confirm_plan_to_calendar",
                "reject_plan",
                "ask_clarification",
                "answer_question",
            ],
        }
        gemma_json = await self.gemma.generate_json(
            schema_name="IntentClassification",
            system_prompt=(
                "Classify a calendar/planning assistant user message. Return a JSON object matching "
                "IntentClassification with keys intent, confidence, is_calendar_mutation, requires_planning, "
                "requires_calendar_read, requires_user_confirmation, complexity_hint, planning_scope, reason. "
                "If an active plan exists and the user asks for more/intense/better/other days, use "
                "modify_existing_plan, not create_single_event. If the user confirms or rejects an active plan, "
                "use confirm_plan_to_calendar or reject_plan."
            ),
            payload=gemma_payload,
            max_output_tokens=settings.nano_max_output_tokens,
        )
        if isinstance(gemma_json, dict):
            try:
                return IntentClassification.model_validate(gemma_json)
            except Exception:
                pass

        if deterministic is not None and deterministic.confidence >= 0.85:
            return deterministic

        return deterministic or IntentClassification(intent="simple_chat", confidence=0.65, reason="Gemma/deterministic fallback.")
