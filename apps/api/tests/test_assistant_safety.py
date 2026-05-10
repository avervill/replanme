from datetime import UTC, datetime, timedelta

from app.schemas.assistant import ExecutionPlan, PlanPreviewChange, PlanStep
from app.services.assistant.execution import SafetyGuard


def test_safety_guard_requires_confirmation_for_bulk_duplication():
    plan = ExecutionPlan(
        goal="duplicate_week",
        summary="Duplicate a week of events",
        selected_model="gpt-4o-mini",
        route="complex",
        reasoning="Bulk duplication",
        response_message="Ready to duplicate events.",
        steps=[
            PlanStep(
                id="step-1",
                action="duplicate_events",
                purpose="Duplicate this week into next week",
                payload={},
            )
        ],
    )
    now = datetime(2026, 4, 24, 9, tzinfo=UTC)
    preview = [
        PlanPreviewChange(
            action="duplicate_events",
            title=f"Event {index}",
            details="Would be duplicated",
            current_start_at=now + timedelta(days=index),
            proposed_start_at=now + timedelta(days=index + 7),
            proposed_end_at=now + timedelta(days=index + 7, hours=1),
        )
        for index in range(6)
    ]

    assessment = SafetyGuard().assess(plan, preview)

    assert assessment.requires_confirmation is True
    assert assessment.risk_level in {"high", "critical"}
    assert assessment.impacted_events == 6


def test_safety_guard_requires_confirmation_for_batch_operations():
    plan = ExecutionPlan(
        goal="move_day",
        summary="Move events in a batch",
        selected_model="gpt-4o-mini",
        route="complex",
        reasoning="Bulk move",
        response_message="Ready to move events.",
        steps=[
            PlanStep(
                id="step-1",
                action="batch_move_events",
                purpose="Move tomorrow's events forward",
                payload={},
            )
        ],
    )

    assessment = SafetyGuard().assess(plan, [])

    assert assessment.requires_confirmation is True
    assert assessment.risk_level == "high"
    assert "Plan moves multiple calendar events." in assessment.reasons
