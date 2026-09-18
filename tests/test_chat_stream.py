"""Test endpoint POST /api/chat/stream lewat ASGI (tanpa server network)."""

from collections.abc import AsyncIterator

import httpx

from app.api.deps import get_streamer
from app.core.sse import SSEEvent
from app.main import app
from tests.sse_utils import parse_frames, tokens_text


async def test_stream_returns_tokens_then_done(client: httpx.AsyncClient) -> None:
    payload = {"message": "apa itu rag"}
    async with client.stream("POST", "/api/chat/stream", json=payload) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join([chunk async for chunk in response.aiter_text()])

    frames = parse_frames(raw)

    assert frames[-1][0] == "done"
    assert "apa itu rag" in tokens_text(frames)


async def test_empty_message_is_rejected_before_stream(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/chat/stream", json={"message": ""})

    assert response.status_code == 422
    assert "text/event-stream" not in response.headers["content-type"]


async def test_source_error_becomes_error_frame(client: httpx.AsyncClient) -> None:
    async def broken_streamer(message: str) -> AsyncIterator[SSEEvent]:
        yield "token", {"text": "mulai "}
        raise RuntimeError("rahasia internal")

    app.dependency_overrides[get_streamer] = lambda: broken_streamer

    payload = {"message": "halo"}
    async with client.stream("POST", "/api/chat/stream", json=payload) as response:
        raw = "".join([chunk async for chunk in response.aiter_text()])

    frames = parse_frames(raw)

    assert frames[0] == ("token", '{"text": "mulai "}')
    assert frames[-1][0] == "error"
    assert "rahasia internal" not in raw
