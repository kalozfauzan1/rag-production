"""Dependency FastAPI — titik sambung yang bisa diganti saat test."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.sse import SSEEvent, Streamer
from app.schemas.chat import DoneData, TokenData
from app.services.fake_llm import stream_fake_answer


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
