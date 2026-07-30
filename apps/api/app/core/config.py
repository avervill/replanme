"""Typed runtime configuration for the Replanme API."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cryptography.fernet import Fernet
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def discover_env_files() -> tuple[Path | str, ...]:
    config_path = Path(__file__).resolve()
    candidates = [parent / ".env" for parent in config_path.parents]
    candidates.append(".env")
    return tuple(dict.fromkeys(path for path in candidates if path == ".env" or path.exists()))


class Settings(BaseSettings):
    app_name: str = "Replanme API"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./replanme.db"
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "KV_URL", "UPSTASH_REDIS_URL"),
    )

    frontend_url: str = "http://localhost:3000"
    session_cookie_name: str = "replanme_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    cookie_secure: bool = False
    token_encryption_key: str = ""
    google_allowed_emails: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:3000/api/v1/auth/google/callback"

    openai_api_key: str = ""
    ai_simple_model: str = "gpt-5.6-luna"
    ai_complex_model: str = "gpt-5.6-terra"
    transcription_model: str = "gpt-transcribe"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    plan_ttl_seconds: int = 60 * 30
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    max_upload_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=discover_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgresql://") and "+asyncpg" not in value:
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

        if not value.startswith("postgresql+asyncpg://"):
            return value

        parsed = urlsplit(value)
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        normalized_query: list[tuple[str, str]] = []
        has_ssl = any(key == "ssl" for key, _ in query_items)
        for key, query_value in query_items:
            if key == "channel_binding":
                continue
            if key == "sslmode":
                if not has_ssl:
                    normalized_query.append(("ssl", query_value))
                continue
            normalized_query.append((key, query_value))

        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(normalized_query), parsed.fragment)
        )

    @field_validator("token_encryption_key")
    @classmethod
    def validate_fernet_key(cls, value: str) -> str:
        if not value:
            return value
        try:
            Fernet(value.encode())
        except ValueError as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [self.frontend_url, "http://127.0.0.1:3000"]

    @property
    def google_allowed_email_set(self) -> set[str]:
        return {email.strip().casefold() for email in self.google_allowed_emails.split(",") if email.strip()}

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() == "production"


settings = Settings()
