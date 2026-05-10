"""Helpers for extracting and validating structured JSON from model responses."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def extract_json_object(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.startswith("json"):
            clean = clean[4:]
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end < start:
        raise json.JSONDecodeError("No JSON object found", clean, 0)
    return json.loads(clean[start : end + 1])


def validate_structured_payload(model: type[T], payload: str | dict) -> T:
    try:
        if isinstance(payload, str):
            return model.model_validate(extract_json_object(payload))
        return model.model_validate(payload)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid structured payload for {model.__name__}") from exc

