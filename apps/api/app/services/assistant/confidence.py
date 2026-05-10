"""Cheap heuristics for routing and escalation decisions."""

from __future__ import annotations

import re


SIMPLE_KEYWORDS = {
    "add",
    "create",
    "delete",
    "remove",
    "rename",
    "update",
    "edit",
    "what",
    "show",
    "today",
    "tomorrow",
}

COMPLEX_MARKERS = {
    "duplicate",
    "optimize",
    "reschedule",
    "reorganize",
    "reorganise",
    "plan my",
    "make my week",
    "same as last week",
    "move everything",
    "find time",
    "reduce overload",
    "avoid conflicts",
    "prioritize",
    "prioritise",
    "fit 3",
    "fit three",
    "month",
    "finals",
}

AMBIGUOUS_REFERENCES = {
    "everything",
    "it",
    "them",
    "that",
    "same as",
    "around",
    "less exhausting",
}


def lexical_complexity_score(prompt: str) -> float:
    lowered = prompt.lower()
    tokens = re.findall(r"[a-z0-9']+", lowered)
    token_count = len(tokens)
    score = 0.15 if token_count <= 8 else 0.35

    if any(marker in lowered for marker in COMPLEX_MARKERS):
        score += 0.45
    if any(marker in lowered for marker in AMBIGUOUS_REFERENCES):
        score += 0.2
    if lowered.count(" and ") >= 2 or lowered.count(",") >= 2:
        score += 0.15
    if "week" in lowered or "month" in lowered:
        score += 0.1

    return min(score, 1.0)


def simple_command_score(prompt: str) -> float:
    lowered = prompt.lower()
    tokens = set(re.findall(r"[a-z0-9']+", lowered))
    score = 0.0

    if tokens & SIMPLE_KEYWORDS:
        score += 0.4
    if any(word in lowered for word in ("today", "tomorrow", "pm", "am", ":")):
        score += 0.25
    if any(marker in lowered for marker in COMPLEX_MARKERS):
        score -= 0.35
    if any(marker in lowered for marker in AMBIGUOUS_REFERENCES):
        score -= 0.2
    if len(tokens) <= 12:
        score += 0.15

    return max(0.0, min(score, 1.0))


def should_escalate_to_gpt(prompt: str) -> bool:
    complexity = lexical_complexity_score(prompt)
    simple = simple_command_score(prompt)
    return complexity >= 0.5 or simple <= 0.45

