from app.services import llm


def test_gemma_payload_does_not_use_json_mode(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"can_create": false, "clarification_question": '
                                        '"What time?", "title": null, "description": null, '
                                        '"start_at": null, "end_at": null, "timezone": null, '
                                        '"location": null}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, params, json):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(llm.settings, "google_ai_api_key", "test-key")
    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)

    import asyncio

    asyncio.run(
        llm.extract_calendar_event_from_prompt(
            "add meeting tomorrow",
            timezone="UTC",
        )
    )

    generation_config = captured["json"]["generationConfig"]
    assert "responseMimeType" not in generation_config
