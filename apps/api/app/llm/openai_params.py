"""OpenAI Chat Completions parameter compatibility helpers."""

from __future__ import annotations


def completion_token_param(model: str, max_tokens: int) -> dict[str, int]:
    """Return the supported output-token parameter for the selected model.

    GPT-5-family chat completion models reject the legacy ``max_tokens``
    parameter and require ``max_completion_tokens``. Keep legacy models on
    ``max_tokens`` to avoid changing older production paths.
    """

    normalized = (model or "").casefold()
    if normalized.startswith("gpt-5") or normalized.startswith("o1") or normalized.startswith("o3") or normalized.startswith("o4"):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}

