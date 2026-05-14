"""Model parameter compatibility helpers."""

from __future__ import annotations


def completion_token_param(model: str, max_tokens: int) -> dict[str, int]:
    """Return the supported output-token parameter for the selected model."""

    normalized = (model or "").casefold()
    if normalized.startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}
