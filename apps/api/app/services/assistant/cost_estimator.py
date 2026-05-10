"""Internal credit and token-cost estimation for assistant orchestration."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.assistant.types import AssistantIntent, CreditEstimate

logger = logging.getLogger(__name__)


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else repr(value)
    return max(1, len(text) // 4)


def estimate_credit_cost(intent: AssistantIntent, complexity_score: int, model: str) -> CreditEstimate:
    if intent in {"simple_chat", "answer_question"}:
        credit = 0.0
        reason = "simple chat"
    elif intent in {"create_single_event", "delete_event", "update_event", "move_event"}:
        credit = 0.1
        reason = "simple calendar action"
    elif intent == "optimize_schedule":
        credit = 5.0 if complexity_score > 5 else 3.0
        reason = "schedule optimization"
    elif complexity_score <= 5:
        credit = 2.0 if "exam" in model.casefold() else 1.0
        reason = "small plan"
    elif complexity_score <= 10:
        credit = 3.0
        reason = "weekly or hard plan"
    else:
        credit = 10.0 if "5.5" in model else 5.0
        reason = "deep or compact hard planning"

    return CreditEstimate(
        estimated_credit_cost=credit,
        model_used=model,
        complexity_score=complexity_score,
        reason=reason,
    )


def log_model_cost(*, phase: str, model: str, input_payload: Any, max_output_tokens: int) -> None:
    if not settings.enable_ai_cost_logging:
        return
    input_tokens = estimate_tokens(input_payload)
    logger.info(
        "assistant.model_cost_estimate",
        extra={
            "phase": phase,
            "model": model,
            "estimated_input_tokens": input_tokens,
            "max_output_tokens": max_output_tokens,
        },
    )

