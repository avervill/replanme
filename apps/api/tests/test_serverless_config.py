from __future__ import annotations

from app.core.config import Settings


def test_vercel_marketplace_connection_aliases(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("KV_URL", "rediss://default:secret@example.upstash.io:6379")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:secret@example-pooler.neon.tech/replanme?sslmode=require",
    )

    config = Settings(_env_file=None)

    assert config.redis_url.startswith("rediss://")
    assert config.database_url.startswith("postgresql+asyncpg://")
