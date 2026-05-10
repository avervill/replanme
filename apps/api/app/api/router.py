from fastapi import APIRouter

from app.api.routes import admin, ai, auth, calendar, health, scheduling, subscription, uploads, vision, voice

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(subscription.router, prefix="/subscription", tags=["subscription"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(scheduling.router, prefix="/scheduling", tags=["scheduling"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(vision.router, prefix="/vision", tags=["vision"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
