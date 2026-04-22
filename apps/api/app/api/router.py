from fastapi import APIRouter

from app.api.routes import ai, auth, calendar, health, scheduling, vision, voice

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(scheduling.router, prefix="/scheduling", tags=["scheduling"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(vision.router, prefix="/vision", tags=["vision"])

