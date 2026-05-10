# Multi-Agent Planning Architecture

## Core Flow

1. `RouterAgent`
   - Uses cheap heuristics first.
   - Sends only uncertain or complex requests to GPT routing.
   - Routes simple CRUD to Gemma.

2. `PlannerAgent`
   - GPT-only.
   - Consumes prompt, memory, and bounded calendar context.
   - Emits strict JSON `ExecutionPlan` objects.

3. `ExecutionAgent`
   - Validates every plan step against typed tool inputs.
   - Supports preview, dry-run, retry, rollback, and confirmation gating.

4. `PlanningMemoryService`
   - Persists wake/sleep, work hours, focus windows, energy bands, priorities, and scheduling preferences.

5. `AssistantToolRegistry`
   - Typed tools:
     - `create_event`
     - `edit_event`
     - `delete_event`
     - `duplicate_events`
     - `fetch_events`
     - `move_event`
     - `find_free_slots`
     - `summarize_schedule`
     - `detect_conflicts`
     - `optimize_schedule`

## Folder Structure

```text
apps/api/app/
  api/routes/ai.py
  models/planning_memory.py
  schemas/assistant.py
  services/assistant/
    __init__.py
    confidence.py
    execution.py
    json_utils.py
    memory.py
    orchestrator.py
    planner.py
    prompts.py
    providers.py
    router.py
    tools.py
```

## Confirmation Flow

1. Planner produces an `ExecutionPlan`.
2. Execution agent builds a preview.
3. Safety guard marks bulk/rescheduling/destructive changes as confirmable.
4. Pending plan is stored in Redis with a TTL.
5. Frontend sends `confirm=true` with the `confirmation_token`.
6. Execution agent runs the stored plan with rollback protection.

## Cost Strategy

- Heuristics avoid GPT for obvious CRUD.
- Gemma handles direct commands and response formatting.
- GPT sees only bounded calendar context, not the entire calendar.
- Preview path avoids unnecessary writes.

## Example

Prompt:

`Duplicate this week into next week but move workouts to evenings and avoid conflicts with university.`

Result:

- Router -> `complex`
- Planner -> fetch + duplicate + conflict-aware evening placement plan
- Execution -> preview first
- Safety -> confirmation required
- Confirmation -> execute + optional memory writeback
