import asyncio
from datetime import UTC, datetime

from app.schemas.assistant import (
    CalendarEventSnapshot,
    CreateEventResult,
    ExecutionPlan,
    PlanStep,
    ToolExecutionMetadata,
    UserPlanningMemory,
)
from app.services.assistant.execution import ExecutionAgent


class FakeToolRegistry:
    MUTATING_TOOLS = {"create_event", "edit_event", "delete_event", "move_event", "duplicate_events"}

    def __init__(self):
        self.calls = []

    async def execute(self, *, tool_name, payload, user, db, memory):
        self.calls.append(tool_name)
        if tool_name == "create_event":
            return CreateEventResult(
                success=True,
                metadata=ToolExecutionMetadata(tool="create_event", executed=True),
                created_events=[
                    CalendarEventSnapshot(
                        id="evt-1",
                        title="Workout",
                        start_at=datetime(2026, 4, 25, 19, tzinfo=UTC),
                        end_at=datetime(2026, 4, 25, 20, tzinfo=UTC),
                        timezone="UTC",
                        status="confirmed",
                    )
                ],
                rollback=[{"action": "delete_event", "payload": {"event_id": "evt-1"}}],
            )
        if tool_name == "edit_event":
            raise RuntimeError("calendar patch failed")
        return CreateEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="create_event", executed=True),
        )


def test_execution_rolls_back_when_later_step_fails():
    plan = ExecutionPlan(
        goal="test",
        summary="test",
        selected_model="gpt-4o-mini",
        route="complex",
        reasoning="test",
        response_message="test",
        steps=[
            PlanStep(
                id="step-1",
                action="create_event",
                purpose="Create the first event",
                payload={
                    "title": "Workout",
                    "start_at": "2026-04-25T19:00:00+00:00",
                    "end_at": "2026-04-25T20:00:00+00:00",
                    "timezone": "UTC",
                },
            ),
            PlanStep(
                id="step-2",
                action="edit_event",
                purpose="This will fail",
                payload={"event_id": "evt-2", "title": "Fail"},
            ),
        ],
    )

    agent = ExecutionAgent(FakeToolRegistry())
    result = asyncio.run(
        agent.execute(
            plan=plan,
            user=object(),
            db=None,
            memory=UserPlanningMemory(),
        )
    )

    assert result.status == "failed"
    assert result.rollback_performed is True
    assert "delete_event" in agent.tool_registry.calls

