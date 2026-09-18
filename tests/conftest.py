"""Fixture bersama: app + AsyncClient + settings deterministik."""

from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def settings() -> Settings:
    """Settings test: tanpa baca .env, delay kecil, ping lama supaya tidak mengganggu."""
    return Settings(_env_file=None, fake_token_delay_ms=1, sse_ping_interval_seconds=60)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Client httpx yang bicara ke app lewat ASGI — tanpa server network."""
    app.dependency_overrides[get_settings] = lambda: settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
