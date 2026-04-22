from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse


def parse_voice_command(payload: VoiceCommandRequest) -> VoiceCommandResponse:
    lowered = payload.transcript.lower()

    if "move" in lowered or "reschedule" in lowered:
        intent = "move_event"
    elif "buffer" in lowered or "protect" in lowered:
        intent = "protect_time"
    elif "book" in lowered or "meeting" in lowered:
        intent = "book_event"
    else:
        intent = "clarify"

    return VoiceCommandResponse(
        intent=intent,
        summary=(
            "Parsed the spoken request into a calendar action candidate. "
            "Wire this endpoint to Whisper transcription and your calendar tool layer."
        ),
        suggested_buffer_minutes=15,
    )

