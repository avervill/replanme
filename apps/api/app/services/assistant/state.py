"""Persistent per-session conversation state for the calendar assistant."""

from __future__ import annotations

import json

from redis.asyncio import Redis

from app.core.config import settings
from app.schemas.assistant import ConversationState


class ConversationStateStore:
    def __init__(self, redis_client: Redis):
        self.redis_client = redis_client

    async def load(self, *, user_id: str, session_id: str) -> ConversationState:
        raw = await self.redis_client.get(self._key(user_id, session_id))
        if not raw:
            return ConversationState(session_id=session_id)
        payload = json.loads(raw)
        payload["session_id"] = session_id
        return ConversationState.model_validate(payload)

    async def save(
        self,
        *,
        user_id: str,
        session_id: str,
        state: ConversationState,
    ) -> None:
        await self.redis_client.set(
            self._key(user_id, session_id),
            json.dumps(state.model_dump(mode="json")),
            ex=settings.assistant_conversation_ttl_seconds,
        )

    async def clear(self, *, user_id: str, session_id: str) -> None:
        await self.redis_client.delete(self._key(user_id, session_id))

    def _key(self, user_id: str, session_id: str) -> str:
        return f"assistant:conversation:{user_id}:{session_id}"
