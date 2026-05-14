import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.schemas.assistant import (
    AssistantMessageRequest,
    CalendarEventSnapshot,
    ConversationState,
    CreateEventResult,
    FetchEventsResult,
    PlanExecutionResult,
    ToolExecutionMetadata,
    UserPlanningMemory,
)
from app.services.assistant.intent_classifier import deterministic_intent
from app.services.assistant.model_router import calculate_planning_complexity, select_planner_model
from app.services.assistant.orchestrator import AssistantOrchestrator
from app.services.assistant.plan_critic import deterministic_critic
from app.services.assistant.plan_validator import validate_plan
from app.services.assistant.types import (
    ComplexityInput,
    Constraint,
    IntentClassification,
    PlanningState,
    PlanningWindow,
    PlanSession,
    StructuredPlan,
)
from app.core.config import settings


def _disable_llm(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemma_ai_api_key", "")


class FakeStateStore:
    def __init__(self):
        self.states = {}

    async def load(self, *, user_id: str, session_id: str):
        return self.states.get((user_id, session_id), ConversationState(session_id=session_id))

    async def save(self, *, user_id: str, session_id: str, state):
        self.states[(user_id, session_id)] = state


class FakeMemoryService:
    async def get_memory(self, db, user):
        return SimpleNamespace(memory=UserPlanningMemory())


class FakeRegistry:
    MUTATING_TOOLS = {"create_event"}

    def __init__(self):
        self.created = []
        self.fetch_count = 0

    async def fetch_events(self, payload, *, user, db, memory):
        self.fetch_count += 1
        return FetchEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="fetch_events", executed=True),
            events=[],
            count=0,
        )

    async def create_event(self, payload, *, user, db, memory):
        event = CalendarEventSnapshot(
            id=f"evt-{len(self.created) + 1}",
            title=payload.title,
            description=payload.description,
            start_at=payload.start_at,
            end_at=payload.end_at,
            timezone=payload.timezone,
        )
        self.created.append(event)
        return CreateEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="create_event", executed=True),
            created_events=[event],
        )


class ScarceFreeTimeRegistry(FakeRegistry):
    async def fetch_events(self, payload, *, user, db, memory):
        self.fetch_count += 1
        events = []
        day = payload.start_at.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = payload.end_at.replace(hour=0, minute=0, second=0, microsecond=0)
        index = 0
        while day <= end_day:
            if day.date() == payload.start_at.date():
                busy_start = day.replace(hour=9, minute=0)
            else:
                busy_start = day.replace(hour=7, minute=30)
            busy_end = day.replace(hour=23, minute=30)
            events.append(
                CalendarEventSnapshot(
                    id=f"busy-{index}",
                    title="Fixed commitment",
                    start_at=busy_start,
                    end_at=busy_end,
                    timezone="UTC",
                )
            )
            day += timedelta(days=1)
            index += 1
        return FetchEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="fetch_events", executed=True),
            events=events,
            count=len(events),
        )


def _orchestrator():
    registry = FakeRegistry()
    state = FakeStateStore()
    assistant = AssistantOrchestrator(
        state_store=state,
        memory_service=FakeMemoryService(),
        tool_registry=registry,
    )
    return assistant, state, registry


def _orchestrator_with_registry(registry):
    state = FakeStateStore()
    assistant = AssistantOrchestrator(
        state_store=state,
        memory_service=FakeMemoryService(),
        tool_registry=registry,
    )
    return assistant, state, registry


def _user():
    return SimpleNamespace(id="user-1", timezone="UTC", plan="free")


def test_exam_planning_initial_request_saves_draft_without_calendar_mutation(monkeypatch):
    _disable_llm(monkeypatch)
    monkeypatch.setattr("app.services.assistant.constraint_extractor.datetime", datetime)
    assistant, state, registry = _orchestrator()
    prompt = (
        "I need to prepare for ICT and Anatomy finals, ICT on Wednesday, Anatomy on Friday, "
        "plan preparing for this finals"
    )

    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(prompt=prompt, timezone="UTC", session_id="s1"),
            user=_user(),
            db=None,
        )
    )

    saved = asyncio.run(state.load(user_id="user-1", session_id="s1")).planning_state
    assert response.routing.intent == "PLAN_PERIOD"
    assert response.awaiting_confirmation is True
    assert response.model_used in {"gpt-5.4-mini", "gpt-5.4"}
    assert registry.created == []
    assert saved["active"] is True
    assert saved["latest_plan"]["calendar_actions"] == []
    assert "Should I add this to your calendar?" in response.reply


def test_two_final_plan_meets_quality_when_free_time_exists(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="I have ICT final on Wednesday and Anatomy final on Friday. Plan my preparation for both finals.",
                timezone="UTC",
                session_id="quality-a",
            ),
            user=_user(),
            db=None,
        )
    )
    saved = asyncio.run(state.load(user_id="user-1", session_id="quality-a")).planning_state
    plan = saved["latest_plan"]
    subjects = {session["subject"] for session in plan["sessions"]}
    days = {session["start"][:10] for session in plan["sessions"]}

    assert response.routing.intent == "PLAN_PERIOD"
    assert {"ICT", "Anatomy"}.issubset(subjects)
    assert plan["total_planned_hours"] >= 12
    assert len(days) >= 2
    assert plan["inferred_target_hours"] >= 12
    assert registry.created == []
    assert "1.5 planned hours" not in response.reply


def test_two_final_plan_reports_insufficient_free_time(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator_with_registry(ScarceFreeTimeRegistry())

    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="I have ICT final on Wednesday and Anatomy final on Friday. Plan my preparation for both finals.",
                timezone="UTC",
                session_id="quality-b",
            ),
            user=_user(),
            db=None,
        )
    )
    saved = asyncio.run(state.load(user_id="user-1", session_id="quality-b")).planning_state
    plan = saved["latest_plan"]

    assert plan["total_planned_hours"] < plan["inferred_target_hours"]
    assert "below the" in response.reply or "not enough" in response.reply
    assert "Should I add this to your calendar?" in response.reply
    assert registry.created == []


def test_weak_one_session_generated_plan_is_repaired(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    async def weak_generate(**kwargs):
        start = datetime.fromisoformat(kwargs["free_blocks"][0].start)
        end = start + timedelta(minutes=90)
        return StructuredPlan(
            plan_id="weak",
            intent="generate_plan",
            summary="Built a draft plan with 1.5 planned hours.",
            planning_window=PlanningWindow(
                start=kwargs["extracted"].planning_window_start,
                end=kwargs["extracted"].planning_window_end,
            ),
            sessions=[
                PlanSession(
                    title="ICT preparation",
                    subject="ICT",
                    start=start.isoformat(),
                    end=end.isoformat(),
                    type="study",
                    deadline_related_to="ICT",
                ),
                PlanSession(title="Cooking", start=start.isoformat(), end=end.isoformat(), type="cooking"),
                PlanSession(title="Cooking", start=(start+timedelta(days=1)).isoformat(), end=(start+timedelta(days=1, hours=1)).isoformat(), type="cooking"),
                PlanSession(title="Cooking", start=(start+timedelta(days=2)).isoformat(), end=(start+timedelta(days=2, hours=1)).isoformat(), type="cooking")
            ],
            total_planned_hours=1.5,
            inferred_target_hours=14,
        )

    monkeypatch.setattr(assistant.structured_planner, "generate", weak_generate)
    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="I have ICT final on Wednesday and Anatomy final on Friday. Plan my preparation for both finals.",
                timezone="UTC",
                session_id="quality-c",
            ),
            user=_user(),
            db=None,
        )
    )
    saved = asyncio.run(state.load(user_id="user-1", session_id="quality-c")).planning_state
    plan = saved["latest_plan"]

    assert plan["total_planned_hours"] >= 12
    assert len(plan["sessions"]) > 1
    assert {"ICT", "Anatomy"}.issubset({session["subject"] for session in plan["sessions"]})
    assert "1.5 planned hours" not in response.reply


def test_critic_rejects_technically_valid_overloaded_plan():
    start = datetime(2026, 5, 10, 8, tzinfo=UTC)
    plan = StructuredPlan(
        plan_id="overloaded",
        intent="generate_plan",
        summary="Overloaded",
        planning_window=PlanningWindow(start=start.isoformat(), end=(start + timedelta(days=3)).isoformat()),
        sessions=[
            PlanSession(
                title="ICT preparation",
                subject="ICT",
                start=start.isoformat(),
                end=(start + timedelta(hours=6)).isoformat(),
                type="study",
                deadline_related_to="ICT",
            )
        ],
        total_planned_hours=6,
        inferred_target_hours=5,
    )
    critic = deterministic_critic(
        user_request="Plan ICT final preparation",
        plan=plan,
        deadlines=[],
        constraints=[],
        fixed_events=[],
        free_blocks=[],
        memory=UserPlanningMemory(),
    )

    assert critic.approved is False
    assert any("Split" in instruction or "shorter" in instruction for instruction in critic.repair_instructions)


def test_good_balanced_plan_is_approved_without_repair(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    async def fail_repair(**kwargs):
        raise AssertionError("repair should not be called for a good balanced plan")

    monkeypatch.setattr(assistant.repairer, "repair", fail_repair)
    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="I have ICT final on Wednesday and Anatomy final on Friday. Plan my preparation for both finals.",
                timezone="UTC",
                session_id="quality-d",
            ),
            user=_user(),
            db=None,
        )
    )
    saved = asyncio.run(state.load(user_id="user-1", session_id="quality-d")).planning_state

    assert response.awaiting_confirmation is True
    assert saved["latest_plan"]["total_planned_hours"] >= 12


def test_revision_request_modifies_existing_plan_not_single_event(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()
    initial = (
        "I need to prepare for ICT and Anatomy finals, ICT on Wednesday, Anatomy on Friday, "
        "plan preparing for this finals"
    )
    asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(prompt=initial, timezone="UTC", session_id="s2"),
            user=_user(),
            db=None,
        )
    )
    before = asyncio.run(state.load(user_id="user-1", session_id="s2")).planning_state["latest_plan"]["total_planned_hours"]

    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="3 hours is a little for this finals, add very more hours. you can plan preparation on other days",
                timezone="UTC",
                session_id="s2",
            ),
            user=_user(),
            db=None,
        )
    )
    after_state = asyncio.run(state.load(user_id="user-1", session_id="s2")).planning_state

    assert response.routing.intent == "PLAN_PERIOD"
    assert "When should I schedule" not in response.reply
    assert after_state["latest_plan"]["intent"] == "modify_existing_plan"
    assert after_state["latest_plan"]["total_planned_hours"] > before
    assert registry.created == []


def test_confirmation_creates_calendar_events_from_latest_plan(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()
    asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="I need to prepare for ICT final, ICT on Wednesday, plan preparing for this final",
                timezone="UTC",
                session_id="s3",
            ),
            user=_user(),
            db=None,
        )
    )

    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(prompt="yes, add it to calendar", timezone="UTC", session_id="s3"),
            user=_user(),
            db=None,
        )
    )
    saved = asyncio.run(state.load(user_id="user-1", session_id="s3")).planning_state

    assert response.routing.intent == "CONFIRMATION_YES"
    assert response.execution.created_events
    assert len(registry.created) == len(response.execution.created_events)
    assert saved["confirmed"] is True
    assert saved["created_calendar_event_ids"]


def test_simple_event_classifies_as_create_and_not_planning():
    result = deterministic_intent("add gym tomorrow at 6pm", None)

    assert result.intent == "create_single_event"
    assert result.requires_planning is False


def test_full_week_plan_routes_to_hard_without_deep_for_free_user():
    score = calculate_planning_complexity(
        ComplexityInput(
            intent="optimize_schedule",
            planning_window_days=7,
            fixed_events_count=12,
            constraints_count=5,
            deadlines_count=3,
            requires_energy_optimization=True,
            requires_calendar_rewrite=True,
        )
    )
    selected = select_planner_model(score, user=_user())

    assert score > 5
    assert selected.model == "gpt-5.4"
    assert selected.tier == "hard"


def test_validation_catches_overlapping_sessions():
    start = datetime(2026, 5, 11, 9, tzinfo=UTC)
    plan = StructuredPlan(
        plan_id="p1",
        intent="generate_plan",
        summary="bad",
        planning_window=PlanningWindow(start=start.isoformat(), end=(start + timedelta(days=1)).isoformat()),
        sessions=[
            PlanSession(title="ICT prep", start=start.isoformat(), end=(start + timedelta(hours=2)).isoformat(), type="study"),
            PlanSession(title="Anatomy prep", start=(start + timedelta(hours=1)).isoformat(), end=(start + timedelta(hours=3)).isoformat(), type="study"),
        ],
        total_planned_hours=4,
    )

    result = validate_plan(
        plan,
        fixed_events=[],
        deadlines=[],
        constraints=[],
        memory=UserPlanningMemory(),
    )

    assert result.valid is False
    assert any(issue.code == "session_overlap" for issue in result.issues)


def test_backend_response_reply_is_always_string():
    classification = IntentClassification(intent="simple_chat", reason="test")
    assistant, _, _ = _orchestrator()

    response = assistant._response(
        session_id="s4",
        reply="Readable message",
        memory=UserPlanningMemory(),
        classification=classification,
        selected_model="backend",
        complexity_score=0,
        credit_cost=0,
    )

    assert isinstance(response.reply, str)
    assert "[object Object]" not in response.reply


def test_recurring_tasks_extracted_and_planned(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="Plan my week. I want to go to the gym 3 times, cook daily, and spend 10 hours on my ML project.",
                timezone="UTC",
                session_id="s-recurring",
            ),
            user=_user(),
            db=None,
        )
    )
    saved = asyncio.run(state.load(user_id="user-1", session_id="s-recurring")).planning_state
    plan = saved["latest_plan"]

    assert response.routing.intent == "PLAN_PERIOD"
    
    gym_sessions = [s for s in plan["sessions"] if s["type"] == "gym"]
    assert len(gym_sessions) >= 3

    cooking_sessions = [s for s in plan["sessions"] if s["type"] == "cooking"]
    assert len(cooking_sessions) >= 6  # ~daily

    project_sessions = [s for s in plan["sessions"] if s["type"] == "project"]
    assert len(project_sessions) > 0


def test_title_fragment_cleanup(monkeypatch):
    from app.services.assistant.planner import _clean_session_title
    
    assert _clean_session_title("I have an ICT study session") == "An ICT study session"
    assert _clean_session_title("I have ICT study session") == "ICT study session"
    assert _clean_session_title("and cook dinner") == "Cook dinner"
    assert _clean_session_title("I need 3 hours for project") == "3 hours for project"
    assert _clean_session_title("Gym session") == "Gym session"


def test_validation_catches_bad_title_fragments():
    from app.services.assistant.types import RecurringTask
    start = datetime(2026, 5, 11, 9, tzinfo=UTC)
    plan = StructuredPlan(
        plan_id="p1",
        intent="generate_plan",
        summary="bad",
        planning_window=PlanningWindow(start=start.isoformat(), end=(start + timedelta(days=1)).isoformat()),
        sessions=[
            PlanSession(title="I have ICT prep", start=start.isoformat(), end=(start + timedelta(hours=2)).isoformat(), type="study"),
        ],
        total_planned_hours=2,
    )

    result = validate_plan(
        plan,
        fixed_events=[],
        deadlines=[],
        constraints=[],
        memory=UserPlanningMemory(),
        recurring_tasks=[RecurringTask(name="Project", category="project")],
    )

    assert result.valid is False
    assert any(issue.code == "bad_title" for issue in result.issues)


def test_lifecycle_1_revised_plan_confirmation_applies_revised_plan(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="I need to prepare for ICT final.",
                timezone="UTC",
                session_id="s_lc1",
            ),
            user=_user(),
            db=None,
        )
    )
    plan_A = asyncio.run(state.load(user_id="user-1", session_id="s_lc1")).planning_state["latest_plan"]
    
    asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="add more",
                timezone="UTC",
                session_id="s_lc1",
            ),
            user=_user(),
            db=None,
        )
    )
    plan_B = asyncio.run(state.load(user_id="user-1", session_id="s_lc1")).planning_state["latest_plan"]
    
    assert plan_B["plan_id"] != plan_A["plan_id"]
    assert plan_B["version"] > plan_A["version"]
    assert plan_B["supersedes_plan_id"] == plan_A["plan_id"]
    assert plan_B["status"] == "active_unconfirmed"
    
    conf_response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt="yes",
                timezone="UTC",
                session_id="s_lc1",
                confirmation_token=plan_B["plan_id"],
            ),
            user=_user(),
            db=None,
        )
    )
    assert conf_response.execution.status == "completed"
    plan_B_after = asyncio.run(state.load(user_id="user-1", session_id="s_lc1")).planning_state["latest_plan"]
    assert plan_B_after["status"] == "applied_to_calendar"
    assert len(registry.created) > 0


def test_lifecycle_2_old_plan_cannot_be_confirmed(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="I need to prepare for ICT final.", timezone="UTC", session_id="s_lc2"), user=_user(), db=None))
    plan_A = asyncio.run(state.load(user_id="user-1", session_id="s_lc2")).planning_state["latest_plan"]
    
    asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="add more", timezone="UTC", session_id="s_lc2"), user=_user(), db=None))
    
    conf_response = asyncio.run(
        assistant.handle_message(
            payload=AssistantMessageRequest(prompt="yes", timezone="UTC", session_id="s_lc2", confirmation_token=plan_A["plan_id"]),
            user=_user(),
            db=None,
        )
    )
    assert conf_response.execution.status == "failed"
    assert "safely determine which one to add" in conf_response.reply
    assert len(registry.created) == 0


def test_lifecycle_3_duplicate_confirmation(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="I need to prepare for ICT final.", timezone="UTC", session_id="s_lc3"), user=_user(), db=None))
    
    conf_1 = asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="yes", timezone="UTC", session_id="s_lc3"), user=_user(), db=None))
    assert conf_1.execution.status == "completed"
    
    conf_2 = asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="yes", timezone="UTC", session_id="s_lc3"), user=_user(), db=None))
    assert conf_2.execution.status == "completed"
    assert "already added" in conf_2.reply
    assert len(registry.created) == conf_1.execution.executed_steps


# Note test_lifecycle_4_pending_actions is implicit since plan_B['calendar_actions'] = [] by design

def test_lifecycle_5_sidebar_reopen(monkeypatch):
    _disable_llm(monkeypatch)
    assistant, state, registry = _orchestrator()

    asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="I need to prepare for ICT final.", timezone="UTC", session_id="s_lc5"), user=_user(), db=None))
    asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="add more", timezone="UTC", session_id="s_lc5"), user=_user(), db=None))
    
    # Sidebar re-opens, sending confirmation with token
    plan_B = asyncio.run(state.load(user_id="user-1", session_id="s_lc5")).planning_state["latest_plan"]
    conf = asyncio.run(assistant.handle_message(payload=AssistantMessageRequest(prompt="yes", timezone="UTC", session_id="s_lc5", confirmation_token=plan_B["plan_id"]), user=_user(), db=None))
    assert conf.execution.status == "completed"
