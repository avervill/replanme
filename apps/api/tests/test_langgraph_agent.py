import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.config import settings
from app.schemas.assistant import (
    AssistantMessageRequest,
    CalendarEventSnapshot,
    ConversationState,
    CreateEventResult,
    FetchEventsResult,
    FindFreeSlotsResult,
    FreeSlot,
    OptimizeScheduleResult,
    PlanPreviewChange,
    ToolExecutionMetadata,
    UserPlanningMemory,
)
from app.services.assistant import orchestrator as orchestrator_module
from app.services.assistant.orchestrator import AssistantOrchestrator, _compact_tool_result, _tool_specs


class FakeAIMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeChatOpenAI:
    model_calls = []

    def __init__(self, *, model, api_key):
        self.model = model
        self.api_key = api_key
        self.bound_tool_names = []
        FakeChatOpenAI.model_calls.append(model)

    def bind_tools(self, tools):
        self.bound_tool_names = [tool["function"]["name"] for tool in tools]
        return self

    async def ainvoke(self, messages):
        prompt = next((message["content"] for message in reversed(messages) if message.get("role") == "user"), "")
        has_tool_result = any(message.get("role") == "tool" for message in messages)

        if self.model == settings.ai_simple_model:
            if has_tool_result:
                return FakeAIMessage("Done.")
            if "add gym" in prompt.casefold():
                return FakeAIMessage(
                    tool_calls=[
                        {
                            "id": "simple-create",
                            "name": "create_event",
                            "args": {
                                "title": "gym",
                                "start_at": "2026-05-15T18:00:00+00:00",
                                "end_at": "2026-05-15T19:00:00+00:00",
                                "timezone": "UTC",
                            },
                        }
                    ]
                )
            return FakeAIMessage(
                tool_calls=[
                    {
                        "id": "delegate-plan",
                        "name": "delegate_to_smarter_model",
                        "args": {"task": prompt, "reason": "Planning or optimization needs deeper reasoning."},
                    }
                ]
            )

        if has_tool_result:
            return FakeAIMessage("Draft ready.")

        if "2,3,4,5" in prompt.casefold():
            tool_calls = []
            for repeat in range(2):
                for index, (start_time, end_time) in enumerate(
                    (("17:45", "18:15"), ("18:30", "19:00"), ("19:15", "19:45"), ("20:00", "20:30")),
                    start=2,
                ):
                    tool_calls.append(
                        {
                            "id": f"complex-create-{repeat}-{index}",
                            "name": "create_event",
                            "args": {
                                "title": "Pet Project",
                                "description": "Planned by replanme AI.",
                                "start_at": f"2026-05-14T{start_time}:00+00:00",
                                "end_at": f"2026-05-14T{end_time}:00+00:00",
                                "timezone": "UTC",
                                "dry_run": True,
                            },
                        }
                    )
            return FakeAIMessage(tool_calls=tool_calls)

        title = "Planning block"
        if "pet project" in prompt.casefold():
            title = "Pet project work"
        elif "anatomy" in prompt.casefold():
            title = "Anatomy preparation"
        elif "ict" in prompt.casefold():
            title = "ICT preparation"

        return FakeAIMessage(
            tool_calls=[
                {
                    "id": "complex-create",
                    "name": "create_event",
                    "args": {
                        "title": title,
                        "description": "Planned by replanme AI.",
                        "start_at": "2026-05-14T10:00:00+00:00",
                        "end_at": "2026-05-14T11:30:00+00:00",
                        "timezone": "UTC",
                        "dry_run": True,
                    },
                }
            ]
        )


class InMemoryStateStore:
    def __init__(self):
        self.states = {}

    async def load(self, *, user_id, session_id):
        return self.states.get((str(user_id), session_id), ConversationState(session_id=session_id))

    async def save(self, *, user_id, session_id, state):
        self.states[(str(user_id), session_id)] = state


class FakeMemoryService:
    async def get_memory(self, db, user):
        return SimpleNamespace(memory=UserPlanningMemory())


class FakeRegistry:
    MUTATING_TOOLS = {"create_event", "move_event", "delete_event", "batch_move_events", "batch_delete_events"}

    def __init__(self, *, fail_create=False, duplicate_create=False):
        self.created = []
        self.fetch_count = 0
        self.fetched_payloads = []
        self.fail_create = fail_create
        self.duplicate_create = duplicate_create

    async def create_event(self, payload, *, user, db, memory):
        if self.fail_create:
            raise RuntimeError("calendar create failed")
        if self.duplicate_create and not payload.dry_run and not payload.allow_duplicate:
            raise ValueError("This looks like a duplicate of 'Gym Session' (evt-existing). Do you want to keep both?")
        event = CalendarEventSnapshot(
            id=f"evt-{len(self.created) + 1}",
            title=payload.title,
            description=payload.description,
            start_at=payload.start_at,
            end_at=payload.end_at,
            timezone=payload.timezone,
            location=payload.location,
            status="preview" if payload.dry_run else "confirmed",
            html_link=None,
        )
        if not payload.dry_run:
            self.created.append(event)
        return CreateEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="create_event", executed=not payload.dry_run, dry_run=payload.dry_run),
            created_events=[event],
            preview=[
                PlanPreviewChange(
                    action="create_event",
                    title=event.title,
                    details="Create a new calendar event.",
                    proposed_start_at=event.start_at,
                    proposed_end_at=event.end_at,
                )
            ],
        )

    async def fetch_events(self, payload, *, user, db, memory):
        self.fetch_count += 1
        self.fetched_payloads.append(payload)
        return FetchEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="fetch_events", executed=True),
            events=self.created,
            count=len(self.created),
        )

    async def find_free_slots(self, payload, *, user, db, memory):
        start = payload.start_at.replace(hour=10, minute=0, second=0, microsecond=0)
        return FindFreeSlotsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="find_free_slots", executed=True),
            slots=[
                FreeSlot(start_at=start + timedelta(hours=2 * idx), end_at=start + timedelta(hours=2 * idx + 1), timezone="UTC", score=0.8)
                for idx in range(5)
            ],
        )

    async def optimize_schedule(self, payload, *, user, db, memory):
        return OptimizeScheduleResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="optimize_schedule", executed=False, dry_run=True),
            suggestions=[],
            preview=[
                PlanPreviewChange(
                    action="optimize_schedule",
                    title="Deep work",
                    details="Better focus window.",
                    current_start_at=payload.start_at,
                    proposed_start_at=payload.start_at + timedelta(hours=2),
                    proposed_end_at=payload.start_at + timedelta(hours=3),
                )
            ],
        )


def _assistant(registry=None):
    return AssistantOrchestrator(
        state_store=InMemoryStateStore(),
        memory_service=FakeMemoryService(),
        tool_registry=registry or FakeRegistry(),
    )


def _user():
    return SimpleNamespace(id="user-1", timezone="UTC", plan="free")


def _run(assistant, prompt, *, session_id="s1", **kwargs):
    return asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(prompt=prompt, timezone="UTC", session_id=session_id, preview=False, **kwargs),
            user=_user(),
            db=None,
        )
    )


def _install_fake_llm(monkeypatch):
    FakeChatOpenAI.model_calls = []
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(orchestrator_module, "ChatOpenAI", FakeChatOpenAI)


def test_calendar_tool_result_uses_compact_context():
    result = FetchEventsResult(
        success=True,
        metadata=ToolExecutionMetadata(tool="fetch_events", executed=True),
        events=[
            CalendarEventSnapshot(
                id="evt-1",
                title="Gym",
                description="Leg day",
                start_at=datetime(2026, 5, 14, 18, 0, tzinfo=UTC),
                end_at=datetime(2026, 5, 14, 19, 0, tzinfo=UTC),
                timezone="UTC",
            )
        ],
        count=1,
    )

    content = _compact_tool_result(result, timezone="UTC")

    assert "time zone: UTC" in content
    assert "events count: 1" in content
    assert "title | st_datetime | end_datetime | desc" in content
    assert "Gym | 2026-05-14T18:00:00+00:00 | 2026-05-14T19:00:00+00:00 | Leg day" in content
    assert '"events"' not in content
    assert "{" not in content


def test_create_event_tool_schema_keeps_title_property():
    create_event_spec = next(spec for spec in _tool_specs(("create_event",)) if spec["function"]["name"] == "create_event")

    assert "title" in create_event_spec["function"]["parameters"]["properties"]
    assert "title" in create_event_spec["function"]["parameters"]["required"]


def test_tool_datetime_args_without_offset_are_localized():
    registry = FakeRegistry()
    assistant = _assistant(registry)
    state = {
        "timezone": "Asia/Qyzylorda",
        "user": _user(),
        "db": None,
        "memory": UserPlanningMemory(),
    }

    asyncio.run(
        assistant._execute_tool(
            state,
            "fetch_events",
            {
                "start_at": "2026-05-15T09:00:00+05:00",
                "end_at": "2026-05-15T18:00:00",
            },
            force_dry_run=False,
        )
    )

    payload = registry.fetched_payloads[0]
    assert payload.start_at.isoformat() == "2026-05-15T09:00:00+05:00"
    assert payload.end_at.isoformat() == "2026-05-15T18:00:00+05:00"


def test_missing_create_title_returns_tool_validation_error():
    registry = FakeRegistry()
    assistant = _assistant(registry)
    state = {
        "timezone": "UTC",
        "route": orchestrator_module._initial_agent_route(),
        "messages": [],
        "user": _user(),
        "db": None,
        "memory": UserPlanningMemory(),
        "loop_count": 0,
    }
    state["tool_calls"] = [
        orchestrator_module.ToolCallPlan(
            name="create_event",
            args={
                "start_at": "2026-05-15T18:00:00+00:00",
                "end_at": "2026-05-15T19:00:00+00:00",
                "timezone": "UTC",
            },
            id="missing-title",
        )
    ]

    asyncio.run(assistant._tools_node(state))

    assert state["tool_results"][0]["success"] is False
    assert "missing required field(s): title" in state["tool_results"][0]["error"]
    assert "validation_error" in state["messages"][-1]["content"]


def test_single_create_executes_and_returns_created_event(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    response = _run(_assistant(registry), "add gym tomorrow at 6pm")

    assert response.status == "completed"
    assert response.model_used == "gpt-4o-mini"
    assert response.execution.created_events
    assert registry.created[0].title == "gym"
    assert FakeChatOpenAI.model_calls == ["gpt-4o-mini", "gpt-4o-mini"]


def test_duplicate_create_returns_confirmation_and_applies_with_token(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry(duplicate_create=True)
    assistant = _assistant(registry)

    draft = _run(assistant, "add gym tomorrow at 6pm", session_id="duplicate")

    assert draft.status == "awaiting_confirmation"
    assert draft.awaiting_confirmation is True
    assert draft.confirmation_token
    assert registry.created == []
    assert "duplicate" in draft.execution.preview[0].details

    confirmed = _run(
        assistant,
        "yes",
        session_id="duplicate",
        confirm=True,
        confirmation_token=draft.confirmation_token,
    )

    assert confirmed.status == "completed"
    assert registry.created
    assert registry.created[0].title == "gym"


def test_complex_plan_returns_confirmation_without_mutation(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    response = _run(_assistant(registry), "Plan my week around ICT and Anatomy finals")

    assert response.status == "awaiting_confirmation"
    assert response.awaiting_confirmation is True
    assert response.confirmation_token
    assert response.model_used == "gpt-5.4-mini"
    assert registry.created == []
    assert response.execution.preview
    assert FakeChatOpenAI.model_calls == ["gpt-4o-mini", "gpt-5.4-mini"]


def test_natural_task_today_returns_draft_not_generic(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    response = _run(_assistant(registry), "i need to do my pet project today")

    assert response.status == "awaiting_confirmation"
    assert response.awaiting_confirmation is True
    assert response.model_used == "gpt-5.4-mini"
    assert response.confirmation_token
    assert registry.created == []
    assert response.execution.preview
    assert "Pet project" in response.reply
    assert "Tell me what you want to change" not in response.reply
    assert FakeChatOpenAI.model_calls == ["gpt-4o-mini", "gpt-5.4-mini"]


def test_few_next_days_returns_draft(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    response = _run(_assistant(registry), "i need plan few next days")

    assert response.status == "awaiting_confirmation"
    assert response.awaiting_confirmation is True
    assert response.model_used == "gpt-5.4-mini"
    assert response.confirmation_token
    assert registry.created == []
    assert response.execution.preview
    assert "Tell me what you want to change" not in response.reply
    assert FakeChatOpenAI.model_calls == ["gpt-4o-mini", "gpt-5.4-mini"]


def test_duplicate_model_tool_calls_are_deduped_before_confirmation(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    assistant = _assistant(registry)

    draft = _run(assistant, "lets do 2,3,4,5", session_id="dedupe")

    assert draft.status == "awaiting_confirmation"
    assert len(draft.execution.preview) == 4
    assert draft.reply.count("Pet Project") == 4

    confirmed = _run(
        assistant,
        "yes",
        session_id="dedupe",
        confirm=True,
        confirmation_token=draft.confirmation_token,
    )

    assert confirmed.status == "completed"
    assert len(registry.created) == 4


def test_confirmation_executes_latest_pending_plan(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    assistant = _assistant(registry)
    draft = _run(assistant, "Plan my week around ICT final", session_id="confirm")

    confirmed = _run(
        assistant,
        "yes",
        session_id="confirm",
        confirm=True,
        confirmation_token=draft.confirmation_token,
    )

    assert confirmed.status == "completed"
    assert confirmed.execution.created_events
    assert registry.created


def test_old_confirmation_token_cannot_execute_superseded_plan(monkeypatch):
    _install_fake_llm(monkeypatch)
    registry = FakeRegistry()
    assistant = _assistant(registry)
    first = _run(assistant, "Plan my week around ICT final", session_id="supersede")
    second = _run(assistant, "Plan my week around Anatomy final", session_id="supersede")

    response = _run(
        assistant,
        "yes",
        session_id="supersede",
        confirm=True,
        confirmation_token=first.confirmation_token,
    )

    assert first.confirmation_token != second.confirmation_token
    assert response.status == "failed"
    assert registry.created == []


def test_calendar_mutation_failure_returns_failed_response(monkeypatch):
    _install_fake_llm(monkeypatch)
    response = _run(_assistant(FakeRegistry(fail_create=True)), "add gym tomorrow at 6pm")

    assert response.status == "failed"
    assert "calendar create failed" in response.reply
