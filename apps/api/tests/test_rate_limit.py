from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import rate_limit
from app.core.config import settings


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_window_budget(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(rate_limit, "get_redis", lambda: _async_value(fake_redis))
    await rate_limit.enforce_rate_limit(object(), bucket="assistant", identity="user")
    await rate_limit.enforce_rate_limit(object(), bucket="assistant", identity="user")
    with pytest.raises(HTTPException) as exc:
        await rate_limit.enforce_rate_limit(object(), bucket="assistant", identity="user")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"


async def _async_value(value):
    return value
