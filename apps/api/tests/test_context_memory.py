import asyncio

from app.services.assistant.conversation_memory import AgentMemoryHandler, MAX_REPLAY_HISTORY_MESSAGES, MAX_STORED_HISTORY_MESSAGES
from app.schemas.assistant import ConversationState


class InMemoryStateStore:
    def __init__(self):
        self.states = {}

    async def load(self, *, user_id, session_id):
        return self.states.get((user_id, session_id), ConversationState(session_id=session_id))

    async def save(self, *, user_id, session_id, state):
        self.states[(user_id, session_id)] = state


def test_last_event_round_trip():
    async def run():
        handler = AgentMemoryHandler(InMemoryStateStore(), "user-1", "session-1")

        await handler.update_last_event("event-1", "Gym")
        state = await handler._load_state()

        assert await handler.get_last_event() == ("event-1", "Gym")
        assert state.last_active_event_id == "event-1"

    asyncio.run(run())


def test_user_constraints_round_trip_without_duplicates():
    async def run():
        handler = AgentMemoryHandler(InMemoryStateStore(), "user-1", "session-1")

        await handler.add_user_constraint("I work from 9 to 6")
        await handler.add_user_constraint("I work from 9 to 6")
        await handler.add_user_constraint("No events after 10 PM")

        assert await handler.get_user_constraints() == [
            "I work from 9 to 6",
            "No events after 10 PM",
        ]

    asyncio.run(run())


def test_history_window_stores_small_window_and_replays_latest_messages():
    async def run():
        handler = AgentMemoryHandler(InMemoryStateStore(), "user-1", "session-1")
        messages = [{"role": "user", "content": f"message-{index}"} for index in range(70)]

        await handler.append_messages(messages)
        state = await handler._load_state()
        history = await handler.get_history()

        assert len(state.messages) == MAX_STORED_HISTORY_MESSAGES
        assert state.messages[0]["content"] == "message-58"
        assert len(history) == MAX_REPLAY_HISTORY_MESSAGES
        assert history[0]["content"] == "message-65"
        assert history[-1]["content"] == "message-69"

    asyncio.run(run())
