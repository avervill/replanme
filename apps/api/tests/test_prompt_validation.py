import pytest

from app.api.routes.ai import visible_chat_history_messages
from app.schemas.assistant import AssistantMessageRequest


@pytest.mark.parametrize(
    "prompt",
    ["yes", "no", "ok", "move it", "later", "make it shorter"],
)
def test_short_follow_up_prompts_are_accepted(prompt):
    request = AssistantMessageRequest(prompt=prompt)

    assert request.prompt == prompt


def test_chat_history_hides_internal_tool_messages():
    messages = visible_chat_history_messages([
        {"role": "user", "content": "delete gym"},
        {"role": "assistant", "tool_calls": [{"id": "call-1"}], "content": None},
        {"role": "tool", "name": "delete_event", "content": '{"tool":"delete_event","success":true}'},
        {"role": "assistant", "content": "Deleted gym."},
    ])

    assert messages == [
        {"id": "history-0", "role": "user", "text": "delete gym"},
        {"id": "history-3", "role": "assistant", "text": "Deleted gym."},
    ]
