import pytest

from app.schemas.assistant import AssistantMessageRequest


@pytest.mark.parametrize(
    "prompt",
    ["yes", "no", "ok", "move it", "later", "make it shorter"],
)
def test_short_follow_up_prompts_are_accepted(prompt):
    request = AssistantMessageRequest(prompt=prompt)

    assert request.prompt == prompt

