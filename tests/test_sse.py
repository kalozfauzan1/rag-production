"""Unit test inti SSE — tanpa HTTP, cukup async generator biasa."""

import asyncio
from collections.abc import AsyncIterator

from app.core.sse import ERROR_MESSAGE, SSEEvent, format_event, format_ping, sse_stream


def test_format_event_shape() -> None:
    assert format_event("token", {"text": "Apa"}) == 'event: token\ndata: {"text": "Apa"}\n\n'


def test_format_event_keeps_unicode_readable() -> None:
    assert "é" in format_event("token", {"text": "é"})


async def test_stream_forwards_events_in_order() -> None:
    async def source() -> AsyncIterator[SSEEvent]:
        yield "token", {"text": "a"}
        yield "done", {"finish_reason": "stop"}

    frames = [frame async for frame in sse_stream(source(), ping_interval=10)]

    assert frames == [
        format_event("token", {"text": "a"}),
        format_event("done", {"finish_reason": "stop"}),
    ]


async def test_stream_sends_ping_when_source_is_idle() -> None:
    async def slow_source() -> AsyncIterator[SSEEvent]:
        yield "token", {"text": "a"}
        await asyncio.sleep(0.2)
        yield "done", {"finish_reason": "stop"}

    frames = [frame async for frame in sse_stream(slow_source(), ping_interval=0.05)]

    assert format_ping() in frames
    assert frames[-1] == format_event("done", {"finish_reason": "stop"})


async def test_stream_turns_exception_into_error_frame() -> None:
    async def broken_source() -> AsyncIterator[SSEEvent]:
        yield "token", {"text": "a"}
        raise RuntimeError("boom")

    frames = [frame async for frame in sse_stream(broken_source(), ping_interval=10)]

    assert frames[-1] == format_event("error", {"message": ERROR_MESSAGE})
    assert "boom" not in "".join(frames)


async def test_stream_cancels_source_when_consumer_stops() -> None:
    source_stopped = asyncio.Event()

    async def endless_source() -> AsyncIterator[SSEEvent]:
        try:
            for index in range(1000):
                await asyncio.sleep(0.01)
                yield "token", {"text": str(index)}
        finally:
            source_stopped.set()

    stream = sse_stream(endless_source(), ping_interval=10)
    async for _frame in stream:
        break
    await stream.aclose()

    assert source_stopped.is_set()
