"""Factory helpers for the multi-agent planning assistant."""

from __future__ import annotations

from app.core.redis import get_redis
from app.services.assistant.memory import PlanningMemoryService
from app.services.assistant.state import ConversationStateStore
from app.services.assistant.tools import AssistantToolRegistry

async def build_assistant_orchestrator():
    """Creates the primary assistant orchestrator."""
    from app.services.assistant.orchestrator import AssistantOrchestrator

    redis_client = await get_redis()
    tool_registry = AssistantToolRegistry()
    state_store = ConversationStateStore(redis_client)
    memory_service = PlanningMemoryService()
    
    return AssistantOrchestrator(
        state_store=state_store,
        memory_service=memory_service,
        tool_registry=tool_registry,
    )
