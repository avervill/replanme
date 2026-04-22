from typing import Literal

from pydantic import BaseModel


class VoiceCommandRequest(BaseModel):
    transcript: str
    timezone: str = "UTC"


class VoiceCommandResponse(BaseModel):
    intent: Literal["book_event", "move_event", "protect_time", "clarify"]
    summary: str
    suggested_buffer_minutes: int = 15

