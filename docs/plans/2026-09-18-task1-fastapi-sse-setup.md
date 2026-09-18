# Task 1 — FastAPI + Pydantic + Async + SSE: Implementation Plan

> **Untuk eksekutor:** kerjakan plan ini task demi task, jangan lompat. Setiap task
> punya siklus test sendiri dan berakhir commit. Jangan tandai selesai sebelum
> perintah verifikasinya benar-benar dijalankan dan hasilnya sesuai.

**Goal:** Server FastAPI dengan endpoint streaming SSE yang protokolnya benar — frame
terformat, heartbeat saat idle, error setelah stream mulai jadi frame `error`, dan stream
berhenti rapi saat client disconnect.

**Architecture:** Sumber jawaban (async generator) → wrapper protokol SSE
(`app/core/sse.py`) → `StreamingResponse`. Route hanya menyambungkan keduanya lewat
dependency yang bisa di-override saat test, sehingga penggantian sumber jawaban di task 5
tidak menyentuh lapisan protokol.

**Tech Stack:** Python 3.13 (via uv), FastAPI, Pydantic v2 + pydantic-settings, uvicorn,
pytest + pytest-asyncio + httpx, ruff.

**Spec:** `docs/specs/2026-09-18-task1-fastapi-sse-setup-design.md`

## Global Constraints

- Semua perintah Python lewat `uv run …` / `uv add`; **jangan** pakai `python`/`pip` global (mesin ini defaultnya 3.10.6).
- Python 3.13 dipin di `.python-version`; `uv.lock` ikut di-commit.
- Tidak ada secret di repo: `.env` di-ignore, `.env.example` hanya placeholder.
- Komentar & docstring **Bahasa Indonesia** (menjelaskan *kenapa*, bukan mengulang *apa*); identifier dan nama file Bahasa Inggris.
- Satu modul = satu tanggung jawab; file dijaga kecil.
- Setiap commit memakai pesan konvensional (`chore:`, `feat:`, `test:`, `docs:`) dan trailer co-author.
- Perintah di plan ini ditulis untuk PowerShell (Windows).

## Peta file

| File | Tanggung jawab | Task |
| --- | --- | --- |
| `pyproject.toml` | metadata project, dependency, config ruff + pytest | 1 |
| `.python-version`, `.env.example`, `.gitignore` | pin interpreter, contoh config, ignore artefak | 1 |
| `app/core/config.py` | `Settings` (pydantic-settings) + `get_settings()` | 2 |
| `app/api/routes/health.py` | `GET /health` | 2 |
| `app/main.py` | `create_app()`: CORS, router, `/demo` | 2, 5 |
| `tests/conftest.py` | fixture `settings` + `client` (httpx ASGI) | 2 |
| `tests/test_health.py`, `tests/test_app.py` | test level aplikasi | 2, 5 |
| `app/core/sse.py` | format frame, heartbeat, error, cancellation | 3 |
| `tests/test_sse.py` | unit test inti SSE (tanpa HTTP) | 3 |
| `app/schemas/chat.py` | `ChatRequest`, `TokenData`, `DoneData` | 4 |
| `app/services/fake_llm.py` | generator token palsu (diganti di task 5) | 4 |
| `app/api/deps.py` | `get_streamer()` — titik override test | 4 |
| `app/api/routes/chat.py` | `POST /api/chat/stream` | 4 |
| `tests/sse_utils.py` | helper parsing frame untuk test | 4 |
| `tests/test_chat_stream.py` | test endpoint (happy path, 422, error) | 4 |
| `app/static/stream-demo.html` | halaman uji manual SSE | 5 |
| `docs/learning/fastapi-async-sse.md`, `README.md`, `AGENTS.md` | dokumentasi + hasil percobaan manual | 6 |

---

## Task 1: Toolchain & skeleton project

**Files:**
- Create: `pyproject.toml`, `.env.example`
- Modify: `.gitignore`
- Generated: `.python-version`, `uv.lock`

**Interfaces:**
- Consumes: —
- Produces: environment Python 3.13 + dependency terpasang (`fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`) dan dev tools (`pytest`, `pytest-asyncio`, `httpx`, `ruff`) — dipakai semua task berikutnya.

- [ ] **Step 1: Buat `pyproject.toml` (tanpa dependency dulu; `uv add` yang mengisi)**

```toml
[project]
name = "rag-production"
version = "0.1.0"
description = "Lab belajar RAG: dari naif sampai produksi"
readme = "README.md"
requires-python = ">=3.13"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]
```

`pythonpath = ["."]` dipakai supaya `import app` bisa dari mana saja tanpa memasang
project ini sebagai package — di sini `app/` adalah aplikasi, bukan library.

- [ ] **Step 2: Pin interpreter & tambahkan dependency**

```powershell
uv python pin 3.13
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings
uv add --dev pytest pytest-asyncio httpx ruff
```

`uv add` menulis versi ril hasil resolusi ke `pyproject.toml` + `uv.lock`; itulah
pin yang sesungguhnya (bukan angka yang diketik manual di plan ini).

- [ ] **Step 3: Verifikasi environment**

```powershell
uv run python -c "import fastapi, pydantic, pydantic_settings, uvicorn; print('deps ok')"
uv run pytest --version
uv run ruff check .
```

Expected: `deps ok`, versi pytest tampil, ruff tidak menemukan error.

- [ ] **Step 4: Buat `.env.example` (placeholder, tanpa secret)**

```dotenv
# Origin frontend yang diizinkan (Next.js dev di task 7)
CORS_ORIGINS=http://localhost:3000
# Jeda antar token palsu (ms) — naikkan untuk menguji heartbeat
FAKE_TOKEN_DELAY_MS=60
# Interval heartbeat SSE saat stream idle (detik)
SSE_PING_INTERVAL_SECONDS=15
```

- [ ] **Step 5: Tambahkan artefak Python ke `.gitignore`**

Tambahkan di akhir `.gitignore` yang sudah ada:

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml uv.lock .python-version .env.example .gitignore
@'
chore: set up uv project with fastapi, pytest, and ruff

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 2: App factory, `/health`, CORS, dan test harness

**Files:**
- Create: `app/__init__.py`, `app/core/__init__.py`, `app/api/__init__.py`, `app/api/routes/__init__.py`, `app/schemas/__init__.py`, `app/services/__init__.py` (semuanya kosong), `app/core/config.py`, `app/api/routes/health.py`, `app/main.py`
- Test: `tests/__init__.py` (kosong), `tests/conftest.py`, `tests/test_health.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: dependency dari Task 1.
- Produces:
  - `Settings` (field: `cors_origins: str`, `fake_token_delay_ms: int`, `sse_ping_interval_seconds: float`, property `cors_origin_list: list[str]`)
  - `get_settings() -> Settings`
  - `create_app() -> FastAPI` dan objek `app` di `app/main.py`
  - fixture pytest `settings` dan `client`

- [ ] **Step 1: Tulis test yang gagal — `tests/test_health.py`**

```python
"""Test endpoint /health."""

import httpx


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Tulis test yang gagal — `tests/test_app.py`**

```python
"""Test perilaku level aplikasi (middleware, halaman statis)."""

import httpx


async def test_cors_headers_for_frontend_origin(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
```

- [ ] **Step 3: Tulis fixture — `tests/conftest.py`**

```python
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
```

- [ ] **Step 4: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_health.py tests/test_app.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 5: Buat file `__init__.py` kosong**

```powershell
New-Item -ItemType File app/__init__.py, app/core/__init__.py, app/api/__init__.py, app/api/routes/__init__.py, app/schemas/__init__.py, app/services/__init__.py, tests/__init__.py
```

- [ ] **Step 6: Implementasi `app/core/config.py`**

```python
"""Konfigurasi aplikasi dari environment / file .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Semua knob runtime; default-nya nilai dev yang aman."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_origins: str = "http://localhost:3000"
    fake_token_delay_ms: int = 60
    sse_ping_interval_seconds: float = 15.0

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS boleh berisi beberapa origin, dipisah koma."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Dibaca sekali per proses; di test di-override lewat dependency_overrides."""
    return Settings()
```

- [ ] **Step 7: Implementasi `app/api/routes/health.py`**

```python
"""Endpoint pengecekan kesehatan service."""

from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Dipakai uptime check / load balancer (Railway, Fly)."""
    return {"status": "ok"}
```

- [ ] **Step 8: Implementasi `app/main.py`**

```python
"""Titik masuk ASGI: app factory, CORS, dan router."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="rag-production API", version="0.1.0")

    # Frontend Next.js (task 7) jalan di origin berbeda saat dev,
    # jadi browser butuh izin CORS eksplisit.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)

    return app


app = create_app()
```

- [ ] **Step 9: Jalankan test — harus LULUS**

```powershell
uv run pytest -v
uv run ruff check .
```

Expected: 2 passed, ruff bersih.

- [ ] **Step 10: Commit**

```powershell
git add app tests
@'
feat: add app factory with health endpoint and CORS

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 3: Inti SSE — format frame, heartbeat, error, cancellation

**Files:**
- Create: `app/core/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `SSEEvent = tuple[str, dict[str, Any]]`
  - `Streamer = Callable[[str], AsyncIterator[SSEEvent]]`
  - `ERROR_MESSAGE: str`
  - `format_event(event: str, data: dict[str, Any]) -> str`
  - `format_ping() -> str`
  - `sse_stream(events: AsyncIterator[SSEEvent], *, ping_interval: float) -> AsyncIterator[str]`

- [ ] **Step 1: Tulis test yang gagal — `tests/test_sse.py`**

```python
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
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_sse.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.sse'`.

- [ ] **Step 3: Implementasi `app/core/sse.py`**

```python
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
```

- [ ] **Step 4: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_sse.py -v
uv run ruff check .
```

Expected: 6 passed, ruff bersih.

- [ ] **Step 5: Commit**

```powershell
git add app/core/sse.py tests/test_sse.py
@'
feat: add SSE core with heartbeat, error frame, and cancellation

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 4: Endpoint `POST /api/chat/stream`

**Files:**
- Create: `app/schemas/chat.py`, `app/services/fake_llm.py`, `app/api/deps.py`, `app/api/routes/chat.py`, `tests/sse_utils.py`, `tests/test_chat_stream.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `sse_stream`, `SSEEvent`, `Streamer` (Task 3); `Settings`, `get_settings` (Task 2).
- Produces:
  - `ChatRequest(message: str)`, `TokenData(text: str)`, `DoneData(finish_reason: str)`
  - `stream_fake_answer(message: str, *, token_delay_seconds: float) -> AsyncIterator[str]`
  - `get_streamer(settings: Settings = Depends(get_settings)) -> Streamer`
  - `chat.router` dengan `POST /api/chat/stream`
  - `parse_frames(raw: str) -> list[tuple[str, str]]`, `tokens_text(frames) -> str` (helper test)

- [ ] **Step 1: Tulis helper test — `tests/sse_utils.py`**

```python
"""Helper test: memecah body SSE mentah menjadi frame."""

import json


def parse_frames(raw: str) -> list[tuple[str, str]]:
    """Kembalikan daftar (nama_event, data). Heartbeat dilaporkan sebagai ("ping", "")."""
    frames: list[tuple[str, str]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        if block.lstrip().startswith(":"):
            frames.append(("ping", ""))
            continue
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = line.removeprefix("data:").strip()
        frames.append((event, data))
    return frames


def tokens_text(frames: list[tuple[str, str]]) -> str:
    """Gabungkan payload semua event `token` menjadi teks jawaban."""
    return "".join(json.loads(data)["text"] for event, data in frames if event == "token")
```

- [ ] **Step 2: Tulis test yang gagal — `tests/test_chat_stream.py`**

```python
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
```

- [ ] **Step 3: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_chat_stream.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.deps'`.

- [ ] **Step 4: Implementasi `app/schemas/chat.py`**

```python
"""Kontrak payload untuk endpoint chat."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body request POST /api/chat/stream."""

    message: str = Field(min_length=1, max_length=4000)


class TokenData(BaseModel):
    """Payload event `token`: sepotong teks jawaban."""

    text: str


class DoneData(BaseModel):
    """Payload event `done`: akhir stream yang sukses."""

    finish_reason: str
```

- [ ] **Step 5: Implementasi `app/services/fake_llm.py`**

```python
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
```

- [ ] **Step 6: Implementasi `app/api/deps.py`**

```python
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
```

- [ ] **Step 7: Implementasi `app/api/routes/chat.py`**

```python
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
```

- [ ] **Step 8: Daftarkan router di `app/main.py`**

```python
from app.api.routes import chat, health
```

lalu tambahkan setelah `app.include_router(health.router)`:

```python
    app.include_router(chat.router)
```

- [ ] **Step 9: Jalankan test — harus LULUS**

```powershell
uv run pytest -v
uv run ruff check .
```

Expected: 11 passed (2 + 6 + 3), ruff bersih.

- [ ] **Step 10: Commit**

```powershell
git add app tests
@'
feat: add POST /api/chat/stream endpoint with fake token source

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 5: Halaman demo untuk uji manual

**Files:**
- Create: `app/static/stream-demo.html`
- Modify: `app/main.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `POST /api/chat/stream` (Task 4).
- Produces: `GET /demo` → `text/html`.

- [ ] **Step 1: Tulis test yang gagal — tambahkan ke `tests/test_app.py`**

```python
async def test_demo_page_is_served(client: httpx.AsyncClient) -> None:
    response = await client.get("/demo")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_app.py -v
```

Expected: FAIL — `assert 404 == 200`.

- [ ] **Step 3: Buat `app/static/stream-demo.html`**

```html
<!doctype html>
<html lang="id">
  <head>
    <meta charset="utf-8" />
    <title>SSE stream demo</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 60rem; }
      form { display: flex; gap: 0.5rem; }
      input { flex: 1; padding: 0.5rem; }
      button { padding: 0.5rem 1rem; }
      #answer { min-height: 3rem; border: 1px solid #ccc; padding: 0.5rem; white-space: pre-wrap; }
      pre { background: #111; color: #6f6; padding: 1rem; overflow: auto; max-height: 20rem; }
    </style>
  </head>
  <body>
    <h1>Demo streaming SSE</h1>
    <p>
      Halaman ini memakai <code>fetch</code> + <code>ReadableStream</code> (bukan
      <code>EventSource</code>) karena endpoint-nya POST dan mengirim body.
    </p>
    <form id="form">
      <input id="message" value="Apa itu RAG?" />
      <button type="submit" id="send">Kirim</button>
      <button type="button" id="stop" disabled>Stop</button>
    </form>

    <h2>Jawaban</h2>
    <div id="answer"></div>

    <h2>Frame mentah</h2>
    <pre id="raw"></pre>

    <script>
      const form = document.getElementById("form");
      const answerEl = document.getElementById("answer");
      const rawEl = document.getElementById("raw");
      const stopButton = document.getElementById("stop");
      let controller = null;
      let buffer = "";

      function handleFrame(frame) {
        if (frame.startsWith(":")) return; // heartbeat
        const event = frame.match(/^event: (.*)$/m)?.[1];
        const data = frame.match(/^data: (.*)$/m)?.[1];
        if (!event || !data) return;
        const payload = JSON.parse(data);
        if (event === "token") answerEl.textContent += payload.text;
        if (event === "done") answerEl.textContent += "\n\n[selesai]";
        if (event === "error") answerEl.textContent += `\n\n[error] ${payload.message}`;
      }

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        answerEl.textContent = "";
        rawEl.textContent = "";
        buffer = "";
        controller = new AbortController();
        stopButton.disabled = false;

        try {
          const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: document.getElementById("message").value }),
            signal: controller.signal,
          });
          const reader = response.body.getReader();
          const decoder = new TextDecoder();

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            rawEl.textContent += chunk;
            buffer += chunk;
            let index;
            while ((index = buffer.indexOf("\n\n")) !== -1) {
              handleFrame(buffer.slice(0, index));
              buffer = buffer.slice(index + 2);
            }
          }
        } catch (error) {
          if (error.name === "AbortError") answerEl.textContent += "\n\n[dihentikan user]";
          else answerEl.textContent += `\n\n[gagal] ${error.message}`;
        } finally {
          stopButton.disabled = true;
          controller = null;
        }
      });

      stopButton.addEventListener("click", () => controller?.abort());
    </script>
  </body>
</html>
```

- [ ] **Step 4: Tambahkan route `/demo` di `app/main.py`**

Tambahkan import:

```python
from pathlib import Path

from fastapi.responses import FileResponse
```

Tambahkan konstanta di atas `create_app`:

```python
STATIC_DIR = Path(__file__).parent / "static"
```

Tambahkan di dalam `create_app()` sebelum `return app`:

```python
    @app.get("/demo", include_in_schema=False)
    async def demo() -> FileResponse:
        """Halaman uji manual untuk melihat frame SSE apa adanya."""
        return FileResponse(STATIC_DIR / "stream-demo.html")
```

- [ ] **Step 5: Jalankan test — harus LULUS**

```powershell
uv run pytest -v
uv run ruff check .
```

Expected: 12 passed, ruff bersih.

- [ ] **Step 6: Commit**

```powershell
git add app tests
@'
feat: add /demo page for manual SSE testing

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 6: Verifikasi manual, dokumentasi, dan penutup

**Files:**
- Create: `docs/learning/fastapi-async-sse.md`
- Modify: `README.md`, `AGENTS.md`, `docs/README.md`

**Interfaces:**
- Consumes: seluruh hasil Task 1–5.
- Produces: catatan hasil percobaan (disconnect, heartbeat) yang jadi rujukan task berikutnya.

- [ ] **Step 1: Jalankan server dan uji dengan curl**

```powershell
uv run uvicorn app.main:app --reload
```

Di terminal kedua:

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/chat/stream -H "Content-Type: application/json" -d "{\"message\": \"apa itu rag\"}"
```

Expected: frame `event: token` muncul bertahap (bukan sekaligus), diakhiri `event: done`.
Catat: apakah terlihat bertahap atau menggumpal — ini bukti streaming bekerja.

- [ ] **Step 2: Uji disconnect**

Jalankan curl di Step 1, tekan `Ctrl+C` di tengah stream, lihat log server.

Expected: baris log `Stream berhenti sebelum 'done' — client disconnect atau dibatalkan`.
Catat perilaku persisnya (apakah pesan muncul, apakah ada traceback) — ini yang diklaim
di spec §5 dan baru terbukti sekarang.

- [ ] **Step 3: Uji heartbeat**

Set di `.env`:

```dotenv
FAKE_TOKEN_DELAY_MS=20000
SSE_PING_INTERVAL_SECONDS=2
```

Jalankan ulang server + curl, lalu amati frame `: ping` muncul di antara token.
Jangan lupa kembalikan nilainya setelah selesai.

- [ ] **Step 4: Tulis `docs/learning/fastapi-async-sse.md`**

Heading yang wajib ada, berurutan:

1. `## Konsep` — async generator, SSE, dan kenapa keduanya cocok (analogi + definisi singkat).
2. `## Wire format` — contoh frame mentah `event:`/`data:`/`: ping` dan arti baris kosong.
3. `## Alur data di repo ini` — diagram ASCII dari route → `Streamer` → `sse_stream` → client.
4. `## Keputusan & kenapa` — producer/consumer + queue, dan kenapa `wait_for` langsung ke `__anext__()` salah (jelaskan mode kegagalannya).
5. `## Hasil percobaan` — tempel output nyata Step 1–3 (curl bertahap, log disconnect, frame ping), termasuk yang tidak sesuai dugaan.
6. `## Failure mode` — tabel: disconnect, exception, proxy buffering, LLM lambat.
7. `## Catatan produksi` — biaya, latency, jumlah koneksi, timeout proxy.
8. `## Cara menjalankan & menguji` — perintah konkret.
9. `## Eksperimen lanjutan` — 2 ide + link referensi resmi (MDN SSE, Starlette responses, FastAPI).

- [ ] **Step 5: Perbarui `README.md`, `docs/README.md`, dan `AGENTS.md`**

- `README.md`: bagian "Cara menjalankan" (`uv sync`, `uv run uvicorn app.main:app --reload`, `uv run pytest`, `uv run ruff check .`) dan ringkasan endpoint.
- `docs/README.md`: status dokumen (spec → disetujui, learning → selesai, plan → selesai) + link plan.
- `AGENTS.md`: bagian *Lingkungan* → Python 3.13 via uv (API) + Node 24 (frontend, task 7), bukan Node.js saja.

- [ ] **Step 6: Verifikasi akhir**

```powershell
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
git status --short
```

Expected: semua test lulus, ruff bersih, tidak ada file tak terduga yang belum di-commit.

- [ ] **Step 7: Commit**

```powershell
git add README.md AGENTS.md docs
@'
docs: add task 1 learning notes and refresh project docs

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```
