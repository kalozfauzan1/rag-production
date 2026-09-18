"""Inti protokol Server-Sent Events (SSE).

Modul ini sengaja tidak tahu isi jawaban. Tugasnya hanya:
1. mengubah pasangan (nama event, data) menjadi frame SSE,
2. menjaga koneksi tetap hidup saat sumber idle (heartbeat),
3. mengubah exception menjadi frame `error` terakhir,
4. berhenti total saat client menutup koneksi.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Satu langkah dalam aliran SSE: ("token", {"text": "Apa"}).
SSEEvent = tuple[str, dict[str, Any]]

# Fungsi yang mengubah pesan user menjadi aliran event.
Streamer = Callable[[str], AsyncIterator[SSEEvent]]

ERROR_MESSAGE = "Terjadi kesalahan saat menghasilkan jawaban."


class _StreamDone:
    """Penanda internal bahwa sumber sudah habis (lebih jelas daripada mengirim None)."""


_STREAM_DONE = _StreamDone()


def format_event(event: str, data: dict[str, Any]) -> str:
    """Frame SSE: baris `event:`, baris `data:` berisi JSON, lalu baris kosong."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_ping() -> str:
    """Komentar SSE (diawali ':'). Client mengabaikannya; proxy melihatnya sebagai trafik."""
    return ": ping\n\n"


async def sse_stream(
    events: AsyncIterator[SSEEvent], *, ping_interval: float
) -> AsyncIterator[str]:
    """Ubah aliran event aplikasi menjadi aliran frame SSE siap kirim.

    Sumber dibaca oleh task terpisah, bukan oleh generator ini. Alasannya:
    saat heartbeat menunggu (timeout), `asyncio.wait_for` membatalkan await
    yang sedang berjalan — kalau await itu adalah `__anext__()` milik sumber,
    generator sumbernya ikut mati. Dengan task terpisah, timeout hanya
    membatalkan `queue.get()`, dan sumber tetap hidup.
    """
    queue: asyncio.Queue[SSEEvent | _StreamDone] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for event in events:
                await queue.put(event)
        except Exception:
            logger.exception("Sumber stream melempar exception")
            await queue.put(("error", {"message": ERROR_MESSAGE}))
        await queue.put(_STREAM_DONE)

    producer = asyncio.create_task(produce())
    finished = False

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=ping_interval)
            except TimeoutError:
                yield format_ping()
                continue
            if isinstance(item, _StreamDone):
                finished = True
                return
            yield format_event(*item)
    finally:
        # Dijalankan baik saat sukses, dibatalkan (client disconnect),
        # maupun saat generator ditutup paksa — jadi sumber tidak pernah
        # dibiarkan berjalan di belakang (nanti: tidak membayar token LLM sia-sia).
        if not finished:
            logger.info("Stream berhenti sebelum `done` — client disconnect atau dibatalkan")
        producer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer
