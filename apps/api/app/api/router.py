from fastapi import APIRouter

from app.api.routes import assistant, auth, calendar, health, imports, plans, voice

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
