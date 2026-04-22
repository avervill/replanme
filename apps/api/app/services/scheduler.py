from datetime import datetime, timedelta

from app.schemas.scheduling import (
    EnergySchedulingRequest,
    EnergySchedulingResponse,
    ScheduledTaskPreview,
    TaskInput,
)


def _sort_tasks(tasks: list[TaskInput]) -> list[TaskInput]:
    priority = {"high": 0, "medium": 1, "low": 2}
    return sorted(tasks, key=lambda item: (priority[item.intensity], -item.estimated_minutes))


def preview_energy_schedule(
    payload: EnergySchedulingRequest,
) -> EnergySchedulingResponse:
    peak_cursor = datetime.combine(payload.date, payload.windows.peak_start)
    balanced_cursor = peak_cursor.replace(hour=12, minute=30)
    slump_cursor = datetime.combine(payload.date, payload.windows.slump_start)
    scheduled: list[ScheduledTaskPreview] = []

    for task in _sort_tasks(payload.tasks):
        if task.intensity == "high":
            start = peak_cursor
            energy = "peak"
            peak_cursor += timedelta(minutes=task.estimated_minutes + 15)
        elif task.intensity == "low":
            start = slump_cursor
            energy = "slump"
            slump_cursor += timedelta(minutes=task.estimated_minutes + 10)
        else:
            start = balanced_cursor
            energy = "balanced"
            balanced_cursor += timedelta(minutes=task.estimated_minutes + 10)

        end = start + timedelta(minutes=task.estimated_minutes)
        scheduled.append(
            ScheduledTaskPreview(
                title=task.title,
                starts_at=start.isoformat(),
                ends_at=end.isoformat(),
                assigned_energy=energy,
            )
        )

    return EnergySchedulingResponse(scheduled=scheduled)

