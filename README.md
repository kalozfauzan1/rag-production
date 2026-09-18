# rag-production

Lab belajar RAG (Retrieval-Augmented Generation) sampai level produksi — dibangun
bertahap, tiap keputusan dijelaskan dan didokumentasikan di `docs/`.

Status saat ini: **task 1 selesai** (fondasi API + streaming SSE). Roadmap lengkap ada di
`AGENTS.md`.

## Stack

| Bagian | Pilihan |
| --- | --- |
| Runtime | Python 3.13 (dikelola `uv`) |
| API | FastAPI + Pydantic v2 + uvicorn |
| Test | pytest + pytest-asyncio + httpx |
| Lint/format | ruff |

## Cara menjalankan

```powershell
uv sync                                  # pasang dependency (uv mengunduh Python 3.13 bila perlu)
Copy-Item .env.example .env              # konfigurasi lokal (opsional)
uv run uvicorn app.main:app --reload     # server di http://127.0.0.1:8000
```

Verifikasi:

```powershell
uv run pytest -v                # test
uv run ruff check .             # lint
uv run ruff format --check .    # cek format
```

## Endpoint

| Endpoint | Fungsi |
| --- | --- |
| `GET /health` | status service |
| `POST /api/chat/stream` | jawaban streaming (SSE: event `token`, `done`, `error`) |
| `GET /demo` | halaman uji manual: frame mentah + tombol Stop untuk menguji disconnect |

Contoh memanggil endpoint stream:

```powershell
'{"message": "apa itu rag"}' | Out-File -Encoding utf8 payload.json
curl.exe -N -X POST http://127.0.0.1:8000/api/chat/stream -H "Content-Type: application/json" -d "@payload.json"
```

Isi jawaban saat ini masih token palsu dari generator lokal — retrieval dan LLM masuk di
task 3–5.

## Dokumentasi

- `docs/README.md` — index semua dokumen
- `docs/decisions.md` — log keputusan (ADR ringkas)
- `docs/learning/fastapi-async-sse.md` — konsep + hasil percobaan task 1
- `docs/specs/`, `docs/plans/` — desain dan rencana per task
