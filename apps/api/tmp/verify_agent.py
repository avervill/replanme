import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.llm.agent import PlannerAgent
from app.llm.memory import AgentMemoryHandler
from app.services.assistant.tools import AssistantToolRegistry
from app.services.assistant.state import ConversationStateStore
from app.services.assistant.memory import PlanningMemoryService
from app.schemas.assistant import AssistantMessageRequest
from app.models.user import User

async def run_sim():
    import redis.asyncio as redis
    rc = redis.Redis(host='localhost', port=6379, db=0)
    
    agent = PlannerAgent(
        state_store=ConversationStateStore(rc),
        memory_service=PlanningMemoryService(),
        tool_registry=AssistantToolRegistry()
    )
    
    # Needs a real DB for get_memory
    engine = create_async_engine("sqlite+aiosqlite:///./test_suite.db")
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    user = User(id="mock_user_123", timezone="UTC")
    req = AssistantMessageRequest(prompt="Move my 3pm meeting to 4pm.", timezone="UTC")

    async with SessionLocal() as db:
        try:
            print("Running test agent response...")
            res = await agent.handle_message(payload=req, user=user, db=db)
            print("Response:", res.reply)
            print("Steps:", len(res.plan.steps) if hasattr(res.plan, 'steps') else "N/A")
        except Exception as e:
            print("Error executing agent:", e)

if __name__ == "__main__":
    asyncio.run(run_sim())
