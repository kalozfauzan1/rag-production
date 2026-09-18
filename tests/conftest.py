"""Fixture bersama: app + AsyncClient + settings deterministik."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.core.jobs import JobRunner
from app.main import app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings test: tanpa baca .env, data di tmp_path, ping lama supaya tidak mengganggu."""
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        fake_token_delay_ms=1,
        sse_ping_interval_seconds=60,
    )


@pytest.fixture(autouse=True)
def fresh_job_runner() -> Iterator[None]:
    """Runner baru per test supaya status job tidak bocor antar-test."""
    previous = app.state.job_runner
    app.state.job_runner = JobRunner()
    yield
    app.state.job_runner = previous


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Client httpx yang bicara ke app lewat ASGI — tanpa server network."""
    app.dependency_overrides[get_settings] = lambda: settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
