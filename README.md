# rag-production

Lab belajar RAG (Retrieval-Augmented Generation) sampai level produksi — dibangun
bertahap, tiap keputusan dijelaskan dan didokumentasikan di `docs/`.

Status: **task 1 selesai** (fondasi API + streaming SSE) dan **task 2 selesai**
(ingestion PDF/HTML/Markdown → recursive chunking). Roadmap lengkap ada di `AGENTS.md`.

## Stack

| Bagian | Pilihan |
| --- | --- |
| Runtime | Python 3.13 (dikelola `uv`) |
| API | FastAPI + Pydantic v2 + uvicorn |
| Ingestion | pdfplumber (PDF), trafilatura (HTML), tiktoken (hitung token) |
| Test | pytest + pytest-asyncio + httpx |
| Lint/format | ruff |

## Cara menjalankan

```powershell
uv sync                                  # pasang dependency (uv mengunduh Python 3.13 bila perlu)
Copy-Item .env.example .env              # konfigurasi lokal (opsional)
uv run uvicorn app.main:app --reload     # server di http://127.0.0.1:8000
```

Catatan: pemakaian pertama `tiktoken` mengunduh kosakata `cl100k_base` (~1,7 MB) ke cache;
sesudah itu bisa dipakai offline.

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
| `POST /api/documents` | unggah dokumen (`.pdf`, `.html`, `.md`, `.txt`) → diproses di background |
| `GET /api/documents` | daftar dokumen + statusnya |
| `GET /api/documents/{id}` | status satu dokumen (+ progres job) |
| `GET /api/documents/{id}/chunks` | isi chunk hasil pemotongan |

Contoh memanggil endpoint stream:

```powershell
'{"message": "apa itu rag"}' | Out-File -Encoding utf8 payload.json
curl.exe -N -X POST http://127.0.0.1:8000/api/chat/stream -H "Content-Type: application/json" -d "@payload.json"
```

Contoh mengunggah dokumen lalu memeriksa hasilnya:

```powershell
curl.exe -sS -X POST http://127.0.0.1:8000/api/documents -F "file=@dokumen.pdf;filename=dokumen.pdf"
curl.exe -sS http://127.0.0.1:8000/api/documents
Get-Content data/documents/*/meta.json -Raw
```

Isi jawaban chat masih token palsu dari generator lokal; retrieval dan LLM masuk di task 3–5.
Hasil ingestion tersimpan di `data/` (tidak masuk git): file asli di `data/uploads/`, metadata
dan chunk di `data/documents/{doc_id}/`.

## Dokumentasi

- `docs/README.md` — index semua dokumen
- `docs/decisions.md` — log keputusan (ADR ringkas)
- `docs/learning/fastapi-async-sse.md` — task 1: async generator, SSE, heartbeat, disconnect
- `docs/learning/ingestion-chunking.md` — task 2: ekstraksi, chunking, hasil percobaan
- `docs/specs/`, `docs/plans/` — desain dan rencana per task
