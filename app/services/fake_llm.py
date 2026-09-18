"""Sumber jawaban palsu — pengganti sementara pipeline RAG (diganti di task 5)."""

import asyncio
import re
from collections.abc import AsyncIterator

_TEMPLATE = (
    "Ini jawaban palsu untuk pertanyaan: {message}. "
    "Belum ada retrieval dan belum ada LLM — token ini dibuat generator lokal "
    "supaya mekanisme streaming SSE bisa diuji dari ujung ke ujung."
)

_TOKEN_PATTERN = re.compile(r"\S+\s*")


async def stream_fake_answer(message: str, *, token_delay_seconds: float) -> AsyncIterator[str]:
    """Hasilkan teks potong demi potong, dengan jeda meniru kecepatan token LLM."""
    text = _TEMPLATE.format(message=message)
    for token in _TOKEN_PATTERN.findall(text):
        await asyncio.sleep(token_delay_seconds)
        yield token
