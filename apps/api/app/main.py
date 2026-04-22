"""Resched.me FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.core.redis import close_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging("DEBUG" if settings.debug else "INFO")
    logger.info("Starting %s", settings.app_name)
    await init_db()
    yield
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    description="API for AI-assisted scheduling, calendar orchestration, and structured life planning.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "online",
        "docs": "/docs",
    }
