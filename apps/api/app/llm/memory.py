"""Chat history handler interacting with Redis state store."""

from __future__ import annotations

from typing import Any

from app.services.assistant.state import ConversationStateStore

MAX_STORED_HISTORY_MESSAGES = 12
MAX_REPLAY_HISTORY_MESSAGES = 5


class AgentMemoryHandler:
    """Handles short-term chat history and event context using the persistent conversation state."""

    def __init__(self, state_store: ConversationStateStore, user_id: str, session_id: str):
        self.state_store = state_store
        self.user_id = user_id
        self.session_id = session_id

    async def _load_state(self):
        return await self.state_store.load(user_id=self.user_id, session_id=self.session_id)

    async def _save_state(self, state):
        await self.state_store.save(
            user_id=self.user_id,
            session_id=self.session_id,
            state=state,
        )

    # ---- Chat history ----

    async def get_history(self, max_messages: int = MAX_REPLAY_HISTORY_MESSAGES) -> list[dict[str, Any]]:
        state = await self._load_state()
        return getattr(state, "messages", [])[-max_messages:]

    async def append_messages(self, messages: list[dict[str, Any]], max_history: int = MAX_STORED_HISTORY_MESSAGES) -> None:
        state = await self._load_state()
        current = getattr(state, "messages", [])
        current.extend(messages)

        # Sliding window, keep the latest N history
        state.messages = current[-max_history:]

        await self._save_state(state)

    async def add_user_message(self, content: str | list[dict[str, Any]]) -> None:
        await self.append_messages([{"role": "user", "content": content}])

    async def add_assistant_message(self, content: str) -> None:
        await self.append_messages([{"role": "assistant", "content": content}])

    async def add_tool_call(self, tool_call_msg: dict[str, Any]) -> None:
        """Adds a message dictionary containing an assistant role and tool_calls list."""
        await self.append_messages([tool_call_msg])
        
    async def add_tool_response(self, tool_id: str, tool_name: str, response: str) -> None:
        await self.append_messages([{
            "role": "tool",
            "tool_call_id": tool_id,
            "name": tool_name,
            "content": response
        }])

    # ---- Event context tracking ----

    async def update_last_event(self, event_id: str, event_title: str) -> None:
        """Track the last referenced event for pronoun resolution ('it', 'that')."""
        state = await self._load_state()
        state.last_event_id = event_id
        state.last_event_title = event_title
        state.last_active_event_id = event_id
        await self._save_state(state)

    async def get_last_event(self) -> tuple[str | None, str | None]:
        """Returns (event_id, event_title) or (None, None)."""
        state = await self._load_state()
        return (
            getattr(state, "last_active_event_id", None) or getattr(state, "last_event_id", None),
            getattr(state, "last_event_title", None),
        )

    async def clear_last_event(self, event_id: str | None = None) -> None:
        """Clear active event state after deletion or failed verification."""
        state = await self._load_state()
        current_id = getattr(state, "last_active_event_id", None) or getattr(state, "last_event_id", None)
        if event_id is None or current_id == event_id:
            state.last_event_id = None
            state.last_event_title = None
            state.last_active_event_id = None
            await self._save_state(state)

    # ---- User constraints ----

    async def add_user_constraint(self, constraint: str) -> None:
        """Store a user-stated constraint (e.g. 'I work from 9 to 6')."""
        state = await self._load_state()
        constraints = getattr(state, "user_constraints", [])
        if constraint not in constraints:
            constraints.append(constraint)
        state.user_constraints = constraints
        await self._save_state(state)

    async def get_user_constraints(self) -> list[str]:
        state = await self._load_state()
        return getattr(state, "user_constraints", [])

    # ---- Conflict resolution mode ----

    async def set_conflict_mode(self, enabled: bool) -> None:
        state = await self._load_state()
        state.conflict_resolution_mode = enabled
        await self._save_state(state)

    async def get_conflict_mode(self) -> bool:
        state = await self._load_state()
        return getattr(state, "conflict_resolution_mode", False)
