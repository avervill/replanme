"""Application configuration with environment validation."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def discover_env_files() -> tuple[Path | str, ...]:
    config_path = Path(__file__).resolve()
    env_files: list[Path | str] = []

    for directory in config_path.parents:
        candidate = directory / ".env"
        if candidate.exists():
            env_files.append(candidate)

    # Fall back to the process working directory for environments that inject
    # a local .env next to the app entrypoint.
    env_files.append(".env")

    seen: set[str] = set()
    unique_env_files: list[Path | str] = []
    for env_file in env_files:
        key = str(env_file)
        if key not in seen:
            seen.add(key)
            unique_env_files.append(env_file)

    return tuple(unique_env_files)


class Settings(BaseSettings):
    app_name: str = "Resched.me API"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # ----- Database -----
    database_url: str = "sqlite+aiosqlite:///./reschedai.db"

    # ----- Redis -----
    redis_url: str = "redis://localhost:6379/0"

    # ----- Auth / Security -----
    secret_key: str = secrets.token_urlsafe(32)
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # ----- Frontend -----
    frontend_url: str = "http://localhost:3000"

    # ----- OpenAI -----
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    whisper_model: str = "gpt-4o-mini-transcribe"
    google_ai_api_key: str = ""
    gemma_model: str = "gemma-3-27b-it"

    # ----- Google OAuth -----
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = (
        "http://localhost:8000/api/v1/auth/google/callback"
    )

    model_config = SettingsConfigDict(
        env_file=discover_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [self.frontend_url, "http://127.0.0.1:3000"]

    @property
    def missing_google_oauth_settings(self) -> list[str]:
        missing: list[str] = []
        if not self.google_client_id:
            missing.append("GOOGLE_CLIENT_ID")
        if not self.google_client_secret:
            missing.append("GOOGLE_CLIENT_SECRET")
        if not self.google_redirect_uri:
            missing.append("GOOGLE_REDIRECT_URI")
        return missing


settings = Settings()
