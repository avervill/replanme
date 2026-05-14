import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.llm.agent import _extract_simple_calendar_command_with_gemma
from app.llm.gemma import GemmaClient
from app.llm.tools import _parse_attachment_text_with_gemma
from app.services.assistant.constraint_extractor import ConstraintExtractor
from app.services.assistant.intent_classifier import IntentClassifier
from app.services.assistant.plan_critic import PlanCritic
from app.services.assistant.plan_repair import PlanRepairer
from app.services.assistant.planner import StructuredPlanner
from app.services.subscriptions import FeatureName, classify_prompt_feature_with_gemma
from app.schemas.assistant import UserPlanningMemory
from app.services.assistant.types import (
    FreeBlock,
    IntentClassification,
    ModelSelection,
    PlanValidationIssue,
    PlanValidationResult,
    PlanningWindow,
    PlanSession,
    StructuredPlan,
)


def _enable_gemma(monkeypatch):
    monkeypatch.setattr(settings, "gemma_ai_api_key", "test-key")
    monkeypatch.setattr(settings, "gemma_model", "gemma-test")
    monkeypatch.setattr(settings, "openai_api_key", "")


def test_intent_classifier_uses_gemma_json(monkeypatch):
    _enable_gemma(monkeypatch)

    async def fake_generate_json(self, **kwargs):
        return {
            "intent": "generate_plan",
            "confidence": 0.93,
            "requires_planning": True,
            "requires_calendar_read": True,
            "requires_user_confirmation": True,
            "complexity_hint": "medium",
            "reason": "Gemma classified planning intent.",
        }

    monkeypatch.setattr(GemmaClient, "generate_json", fake_generate_json)
    result = asyncio.run(IntentClassifier().classify(prompt="спланируй неделю для экзаменов", planning_state=None))

    assert result.intent == "generate_plan"
    assert result.requires_planning is True


def test_feature_classifier_uses_gemma_json(monkeypatch):
    _enable_gemma(monkeypatch)

    async def fake_generate_json(self, **kwargs):
        return {"feature": FeatureName.WEEKLY_PLANNING, "reason": "Weekly planning request."}

    monkeypatch.setattr(GemmaClient, "generate_json", fake_generate_json)

    assert asyncio.run(classify_prompt_feature_with_gemma("составь расписание на неделю")) == FeatureName.WEEKLY_PLANNING


def test_constraint_extractor_uses_gemma_json(monkeypatch):
    _enable_gemma(monkeypatch)
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)

    async def fake_generate_json(self, **kwargs):
        return {
            "deadlines": [{"title": "ICT", "due_at": (now + timedelta(days=3)).isoformat(), "kind": "exam"}],
            "constraints": [{"kind": "study", "value": "Study daily", "minutes_per_day": 120}],
            "recurring_tasks": [{"name": "Gym session", "category": "gym", "frequency": "weekly", "count": 3, "duration_minutes": 60}],
            "planning_window_start": now.isoformat(),
            "planning_window_end": (now + timedelta(days=7)).isoformat(),
            "planning_window_days": 8,
            "target_hours": 12,
            "requires_energy_optimization": False,
            "requires_calendar_rewrite": False,
            "deadlines_count": 1,
            "constraints_count": 1,
        }

    monkeypatch.setattr(GemmaClient, "generate_json", fake_generate_json)
    result = asyncio.run(ConstraintExtractor().extract(prompt="готовь меня к ICT и gym 3 times", now=now, planning_state=None))

    assert result.deadlines[0].title == "ICT"
    assert result.recurring_tasks[0].category == "gym"


def test_simple_calendar_extraction_uses_gemma_json(monkeypatch):
    _enable_gemma(monkeypatch)
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    start = datetime(2026, 5, 11, 0, tzinfo=UTC)

    async def fake_generate_json(self, **kwargs):
        return {
            "intent": "create_single_event",
            "title": "gym",
            "date": "tomorrow",
            "date_value": start.isoformat(),
            "start_time": "18:00",
            "end_time": None,
            "duration_minutes": 60,
            "missing_fields": [],
            "confidence": 0.96,
            "relative_time": None,
            "approximate_time": None,
            "old_time": None,
            "new_time": None,
            "requires_calendar_read": False,
        }

    monkeypatch.setattr(GemmaClient, "generate_json", fake_generate_json)
    result = asyncio.run(_extract_simple_calendar_command_with_gemma("add gym tomorrow at 6pm", now))

    assert result.title == "gym"
    assert result.date_value.date().isoformat() == "2026-05-11"
    assert result.missing_fields == []


def test_planner_critic_repair_use_gemma_json(monkeypatch):
    _enable_gemma(monkeypatch)
    start = datetime(2026, 5, 11, 9, tzinfo=UTC)
    end = start + timedelta(hours=2)
    free_blocks = [FreeBlock(start=start.isoformat(), end=(start + timedelta(hours=4)).isoformat(), minutes=240)]
    extracted = type(
        "Extracted",
        (),
        {
            "deadlines": [],
            "constraints": [],
            "recurring_tasks": [],
            "planning_window_start": start.isoformat(),
            "planning_window_end": (start + timedelta(days=1)).isoformat(),
            "planning_window_days": 2,
            "target_hours": 2,
        },
    )()

    async def fake_generate_json(self, **kwargs):
        if kwargs["schema_name"] == "CriticEvaluation":
            return {"approved": True, "score": 9, "main_reason": "Useful", "problems": [], "repair_instructions": [], "user_satisfaction_risk": "low"}
        return {
            "intent": "generate_plan",
            "summary": "Gemma plan",
            "planning_window": {"start": start.isoformat(), "end": (start + timedelta(days=1)).isoformat()},
            "sessions": [{"title": "Focus block", "start": start.isoformat(), "end": end.isoformat(), "type": "work", "reason_short": "Requested."}],
            "assumptions": [],
            "warnings": [],
            "total_planned_hours": 2,
            "inferred_target_hours": 2,
            "requires_user_confirmation": True,
            "calendar_actions": [],
        }

    monkeypatch.setattr(GemmaClient, "generate_json", fake_generate_json)
    plan = asyncio.run(
        StructuredPlanner().generate(
            prompt="plan work",
            classification=IntentClassification(intent="generate_plan", requires_planning=True),
            extracted=extracted,
            planning_state=None,
            fixed_events_summary=[],
            free_blocks=free_blocks,
            model_selection=ModelSelection(
                model="gemma-test",
                tier="default",
                max_input_tokens=4000,
                max_output_tokens=1000,
                complexity_score=1,
                deep_planning_allowed=False,
            ),
        )
    )
    critic, model = asyncio.run(
        PlanCritic().evaluate(
            user_request="plan work",
            plan=plan,
            deadlines=[],
            constraints=[],
            fixed_events=[],
            free_blocks=free_blocks,
            memory=UserPlanningMemory(),
            complexity_score=1,
        )
    )
    repaired = asyncio.run(
        PlanRepairer().repair(
            plan=StructuredPlan(
                plan_id="p",
                intent="generate_plan",
                summary="bad",
                planning_window=PlanningWindow(start=start.isoformat(), end=(start + timedelta(days=1)).isoformat()),
                sessions=[PlanSession(title="Too long", start=start.isoformat(), end=(start + timedelta(hours=5)).isoformat(), type="work")],
                total_planned_hours=5,
            ),
            validation=PlanValidationResult(valid=False, issues=[PlanValidationIssue(code="overloaded", message="Too long")]),
            free_blocks=free_blocks,
            fixed_events=[],
            deadlines=[],
            constraints=[],
            memory=UserPlanningMemory(),
            original_request="plan work",
        )
    )

    assert plan.summary == "Gemma plan"
    assert critic.approved is True
    assert model == "gemma-test"
    assert repaired.summary == "Gemma plan"


def test_image_text_parser_uses_gemma_json(monkeypatch):
    _enable_gemma(monkeypatch)

    async def fake_generate_json(self, **kwargs):
        return {
            "subjects": ["Math"],
            "topics": ["Derivatives"],
            "schedule_structure": ["Monday 09:00 Math"],
        }

    monkeypatch.setattr(GemmaClient, "generate_json", fake_generate_json)
    subjects, topics, structure = asyncio.run(_parse_attachment_text_with_gemma("Monday 09:00 Math\nTopic: Derivatives"))

    assert subjects == ["Math"]
    assert topics == ["Derivatives"]
    assert structure == ["Monday 09:00 Math"]

