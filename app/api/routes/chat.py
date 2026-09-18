"""Endpoint chat dengan streaming SSE."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_streamer
from app.core.config import Settings, get_settings
from app.core.sse import Streamer, sse_stream
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Tanpa header ini, proxy/CDN bisa menahan buffer dan token baru muncul
# sekaligus di akhir — streaming-nya jadi tidak terasa.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    streamer: Annotated[Streamer, Depends(get_streamer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Kirim jawaban sebagai aliran frame SSE."""
    events = streamer(payload.message)
    return StreamingResponse(
        sse_stream(events, ping_interval=settings.sse_ping_interval_seconds),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
