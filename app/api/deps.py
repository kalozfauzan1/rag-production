"""Dependency FastAPI — titik sambung yang bisa diganti saat test."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.jobs import JobRunner
from app.core.sse import SSEEvent, Streamer
from app.schemas.chat import DoneData, TokenData
from app.services.fake_llm import stream_fake_answer
from app.services.ingestion.store import DocumentStore


def get_streamer(settings: Annotated[Settings, Depends(get_settings)]) -> Streamer:
    """Kembalikan fungsi `message -> aliran event`.

    Test mengganti isi dependency ini untuk mensimulasikan error atau skenario
    lain tanpa menyentuh route.
    """

    async def streamer(message: str) -> AsyncIterator[SSEEvent]:
        async for token in stream_fake_answer(
            message, token_delay_seconds=settings.fake_token_delay_ms / 1000
        ):
            yield "token", TokenData(text=token).model_dump()
        yield "done", DoneData(finish_reason="stop").model_dump()

    return streamer


def get_store(settings: Annotated[Settings, Depends(get_settings)]) -> DocumentStore:
    """Store dibuat per request; isinya hanya path, jadi murah."""
    return DocumentStore(uploads_dir=settings.uploads_dir, documents_dir=settings.documents_dir)


def get_job_runner(request: Request) -> JobRunner:
    """Runner hidup di `app.state` supaya ikut siklus hidup aplikasi."""
    runner: JobRunner | None = getattr(request.app.state, "job_runner", None)
    if runner is None:
        raise RuntimeError("job_runner belum dipasang di app.state")
    return runner
