"""Google Gemma JSON generation helpers.

This module is deliberately small and provider-specific. Callers keep their
domain fallbacks and Pydantic validation; Gemma only supplies structured JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

try:  # pragma: no cover - exercised only when google-genai is installed.
    from google import genai
except Exception:  # pragma: no cover - fallback keeps tests importable.
    genai = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class GemmaUnavailable(RuntimeError):
    """Raised when Gemma is not configured or the SDK is unavailable."""


def _loads_json_strict(text: str) -> Any:
    raw = text.strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[len("```json") : -len("```")].strip()
    elif raw.startswith("```") and raw.endswith("```"):
        raw = raw[len("```") : -len("```")].strip()
    return json.loads(raw)


@dataclass
class GemmaClient:
    api_key: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    retry_attempts: int | None = None

    def __post_init__(self) -> None:
        self.api_key = self.api_key if self.api_key is not None else settings.gemma_ai_api_key
        self.model = self.model or settings.gemma_model
        self.timeout_seconds = self.timeout_seconds or settings.gemma_timeout_seconds
        self.retry_attempts = self.retry_attempts or settings.gemma_retry_attempts

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model and genai is not None)

    async def generate_json(
        self,
        *,
        schema_name: str,
        system_prompt: str,
        payload: dict[str, Any],
        max_output_tokens: int,
    ) -> dict[str, Any] | list[Any] | None:
        """Return parsed JSON from Gemma, or None on unavailable/invalid output."""
        if not self.configured:
            return None

        prompt = (
            f"{system_prompt.strip()}\n\n"
            "Return only valid JSON. Do not include markdown, comments, or extra text.\n\n"
            f"Input JSON:\n{json.dumps(payload, ensure_ascii=True, default=str)}"
        )
        attempts = max(1, int(self.retry_attempts or 1))
        for attempt in range(1, attempts + 1):
            try:
                text = await asyncio.wait_for(
                    asyncio.to_thread(self._generate_text, prompt, max_output_tokens),
                    timeout=float(self.timeout_seconds or 60),
                )
                parsed = _loads_json_strict(text)
                if isinstance(parsed, (dict, list)):
                    return parsed
                logger.warning("gemma.invalid_json_root", extra={"schema": schema_name, "root_type": type(parsed).__name__})
                return None
            except Exception as exc:
                logger.warning(
                    "gemma.generate_json_failed",
                    extra={"schema": schema_name, "attempt": attempt, "max_attempts": attempts, "error": type(exc).__name__},
                )
                if attempt >= attempts:
                    return None
        return None

    def _generate_text(self, prompt: str, max_output_tokens: int) -> str:
        if genai is None or not self.api_key:
            raise GemmaUnavailable("Gemma SDK or API key is unavailable.")
        client = genai.Client(api_key=self.api_key)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "contents": prompt,
        }
        if max_output_tokens:
            kwargs["config"] = {
                "max_output_tokens": max_output_tokens,
                "temperature": 0,
            }
        try:
            response = client.models.generate_content(**kwargs)
        except TypeError:
            kwargs.pop("config", None)
            response = client.models.generate_content(**kwargs)
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemma returned empty text.")
        return text
