# Replanme API

FastAPI service for Google Calendar OAuth/CRUD, approval-first LangGraph proposals, in-memory image import, recorded voice transcription, and idempotent plan execution.

```bash
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

See the [repository README](../../README.md) for environment variables, contracts, tests, and deployment.
