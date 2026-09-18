# Task 1 — Setup FastAPI + Pydantic + Async + Streaming SSE

- **Tanggal:** 2026-09-18
- **Status:** draft — menunggu review
- **Posisi:** task 1 dari 9 (roadmap belajar di `AGENTS.md`)

---

## 1. Tujuan & batas

Membangun fondasi backend RAG: server **FastAPI + Pydantic v2 + async + endpoint streaming SSE**, lengkap dengan struktur project, config berbasis `.env`, test, dan dokumentasi.

### Sengaja belum dikerjakan (YAGNI)

- LLM asli, embedding, vector DB, retrieval, citation → task 2–5
- Auth, rate limit, cache, observability → task 9
- Resume stream (`Last-Event-ID`) & auto-reconnect di client → belum ada kebutuhan nyata
- Docker & deploy → task 8

### Justru dikerjakan sekarang (mahal ditambal belakangan)

- **Kontrak event SSE** yang bisa menampung `sources`/`citation` di task 5 tanpa breaking change.
- **Penanganan disconnect & error setelah stream mulai** — setelah header terkirim, status code HTTP tidak bisa diubah lagi; ini harus dipahami sebelum RAG masuk.
- **CORS** untuk frontend Next.js (task 7).

---

## 2. Keputusan

Ringkasan; detail ADR ada di [`docs/decisions.md`](../decisions.md).

| # | Keputusan | Pilihan | Alasan singkat |
| --- | --- | --- | --- |
| D1 | Dependency manager | **uv** 0.11.6 | cepat, ada lockfile, bisa mengunduh interpreter sendiri (system Python 3.10.6 tidak dipakai) |
| D2 | Versi Python | **3.13** via uv (`.python-version`) | wheel native (torch/tiktoken/qdrant-client) lebih aman daripada 3.14; ganti versi nanti cukup `uv python pin` |
| D3 | Implementasi SSE | **manual** (`StreamingResponse`) | tujuan belajar: wire format, heartbeat, disconnect terlihat langsung; `sse-starlette` dicatat sebagai alternatif produksi |
| D4 | Struktur repo | **FastAPI di root**, `web/` untuk Next.js nanti | Railway/Fly deploy dari root; Vercel diarahkan ke `web/` |
| D5 | Test | **pytest + pytest-asyncio (auto) + httpx AsyncClient** | menguji streaming async seperti client nyata |
| D6 | Lint & format | **ruff** | satu tool, cepat (Rust) |

Versi dependency di-pin lewat `uv.lock` (exact), sedangkan `pyproject.toml` memakai rentang kompatibel; alasannya dibahas di `docs/decisions.md`.

---

## 3. Arsitektur & alur data

```text
Browser / curl / Next.js
   │  POST /api/chat/stream   {"message": "..."}
   ▼
FastAPI route  (app/api/routes/chat.py)
   │  Depends → get_streamer()        ← bisa di-override saat test
   ▼
streamer  ──►  app/services/fake_llm.stream_fake_answer()
   │             async generator: yield potongan teks (delay per kata)
   │             [task 5: diganti pipeline RAG → retrieval, LLM, citation]
   ▼
app/core/sse.py::sse_stream()
   │  - format frame:  event: <nama>\n data: <json>\n\n
   │  - heartbeat ": ping" saat idle lebih lama dari interval
   │  - exception  → frame terakhir "event: error" (tanpa stack trace)
   │  - client putus (cancellation) → log, berhenti
   ▼
StreamingResponse(media_type="text/event-stream")
   ▼
Client menerima frame demi frame (tidak menunggu selesai)
```

**Kenapa dipisah begitu:** `fake_llm` (nanti: RAG service) hanya bertanggung jawab menghasilkan potongan teks — ia tidak tahu apa itu SSE. `sse_stream` hanya bertanggung jawab soal protokol — ia tidak tahu isi jawaban. Route tinggal menyambung keduanya. Saat task 5 mengganti sumber jawaban, `app/core/sse.py` tidak perlu disentuh.

**Tipe yang menyambung kedua sisi** (didefinisikan di `app/core/sse.py`):

```python
SSEEvent = tuple[str, dict[str, Any]]                       # ("token", {"text": "Apa"})
Streamer = Callable[[str], AsyncIterator[SSEEvent]]          # message -> aliran event
```

`get_streamer()` mengembalikan `Streamer` — inilah yang di-override di test untuk mensimulasikan error di tengah stream.

---

## 4. Kontrak API

### 4.1 `GET /health`

```json
{ "status": "ok" }
```

### 4.2 `POST /api/chat/stream`

**Request** (JSON):

```json
{ "message": "Apa itu RAG?" }
```

Pydantic: `message: str`, minimal 1 karakter, maksimal 4000. Jika tidak valid → HTTP **422** (terjadi sebelum stream mulai).

**Response headers:**

```text
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
X-Accel-Buffering: no
Connection: keep-alive
```

`X-Accel-Buffering: no` mencegah nginx (yang dipakai banyak platform deploy) menahan buffer sehingga token baru dikirim saat koneksi selesai — penyebab klasik "streaming kok baru muncul di akhir".

**SSE events (task 1):**

```text
event: token
data: {"text": "Apa"}

event: token
data: {"text": " itu"}

event: done
data: {"finish_reason": "stop"}
```

```text
event: error
data: {"message": "Terjadi kesalahan saat menghasilkan jawaban."}
```

**Aturan kontrak:**

1. Stream sukses diakhiri tepat satu `done`.
2. Error **sebelum** stream mulai → HTTP error biasa (422/500); error **setelah** stream mulai → frame `error` sebagai frame terakhir, status HTTP tetap 200.
3. `data` selalu JSON object → penambahan field tidak memecah client lama.
4. Nama event yang dicadangkan untuk task berikutnya: `sources` (daftar dokumen + skor, task 5). Menambah jenis event baru aman karena client memilih event yang dikenal dan mengabaikan sisanya.

### 4.3 `GET /demo`

Satu halaman HTML statis (vanilla JS) untuk melihat stream secara live: daftar frame mentah di samping teks yang sudah dirender, plus tombol **Stop** untuk menguji perilaku disconnect. Bukan frontend produk — itu task 7.

### 4.4 Konfigurasi (`.env`)

Dibaca `pydantic-settings` di `app/core/config.py`; `.env.example` di-commit dengan nilai default, `.env` asli di-ignore git.

| Variable | Default | Fungsi |
| --- | --- | --- |
| `CORS_ORIGINS` | `http://localhost:3000` | origin yang diizinkan (Next.js dev di task 7) |
| `FAKE_TOKEN_DELAY_MS` | `60` | jeda per token palsu — meniru kecepatan LLM; dinaikkan untuk menguji heartbeat |
| `SSE_PING_INTERVAL_SECONDS` | `15` | interval heartbeat saat stream idle |

Belum ada API key di task ini; variabel secret baru muncul di task 3 (embedding) dan 5 (LLM).

---

## 5. Pola async yang dipakai

- **Async generator** sebagai sumber stream: `StreamingResponse` menerima iterator async apa pun.
- **Heartbeat** saat idle: sumber dibaca oleh task terpisah (producer) yang menaruh event ke `asyncio.Queue`; konsumen menunggu `queue.get()` dengan timeout, dan saat timeout mengirim komentar `: ping`. Koneksi SSE yang diam terlalu lama diputus proxy/load balancer — ini akan sangat terasa ketika LLM butuh belasan detik sebelum token pertama.
  **Kenapa bukan `asyncio.wait_for(source.__anext__(), timeout=...)` langsung:** saat timeout, `wait_for` membatalkan await yang sedang berjalan. Jika yang dibatalkan adalah `__anext__()` milik sumber, `CancelledError` menjalar masuk ke generator sumber dan **mematikannya** — persis di saat kita butuh ia tetap hidup (LLM masih bekerja). Ditemukan saat menyusun implementation plan; detailnya dicatat di `docs/learning/fastapi-async-sse.md`.
- **Cancellation**: saat client menutup koneksi, Starlette membatalkan generator kita → blok `finally` membatalkan task producer sehingga sumber ikut berhenti. Nanti inilah yang mencegah kita membayar token LLM yang sudah ditinggalkan user. **Terverifikasi empiris (Starlette 1.6.0)**: client yang berhenti membaca di tengah stream membuat server mencatat `Stream berhenti sebelum 'done'`, artinya `finally` jalan dan producer dibatalkan.
- **Konsekuensi:** desain producer/konsumen menambah satu sentinel internal (`_StreamDone`) di `app/core/sse.py`; harga kecil yang ditukar dengan sumber yang tidak bisa mati karena heartbeat.
- **Logging:** uvicorn hanya mengonfigurasi logger `uvicorn.*`, sehingga `logger.info()` dari kode aplikasi tidak tampil. `create_app()` memanggil `logging.basicConfig(level=INFO)`. Pesan log ditulis ASCII karena stderr yang dialihkan ke file di Windows memakai encoding locale (body response HTTP tetap UTF-8). Keduanya ditemukan saat verifikasi manual — lihat D8 di `docs/decisions.md`.

---

## 6. Struktur file

```text
rag-production/
├── pyproject.toml              # deps, ruff, pytest
├── uv.lock                     # pin exact (di-commit)
├── .python-version             # 3.13
├── .env.example                # placeholder, tanpa secret
├── app/
│   ├── main.py                 # create_app, CORS, router, /demo
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings) + get_settings
│   │   └── sse.py              # format frame, heartbeat, error, cancellation
│   ├── api/
│   │   ├── deps.py             # get_streamer (titik override untuk test)
│   │   └── routes/
│   │       ├── health.py
│   │       └── chat.py
│   ├── schemas/
│   │   └── chat.py             # ChatRequest + payload tiap event
│   ├── services/
│   │   └── fake_llm.py         # generator token palsu (diganti di task 5)
│   └── static/
│       └── stream-demo.html
├── tests/
│   ├── conftest.py             # app + AsyncClient + override settings
│   ├── test_app.py             # CORS, halaman /demo
│   ├── test_health.py
│   ├── test_sse.py             # unit test inti SSE (tanpa HTTP)
│   ├── sse_utils.py            # helper parsing frame
│   └── test_chat_stream.py
└── docs/                       # README, decisions, learning, specs
```

---

## 7. Strategi test

| Kasus | Yang diuji |
| --- | --- |
| `GET /health` | 200 + body |
| Stream sukses | urutan event `token`… → `done`, isi teks sesuai, `Content-Type: text/event-stream` |
| Request invalid | `message` kosong → 422, tidak ada frame SSE |
| Error di tengah stream | streamer di-override agar melempar exception → frame `error` terakhir, tanpa stack trace di body |
| Heartbeat | unit test `sse_stream` (bukan lewat HTTP): sumber idle > ping interval → ada frame `: ping` |
| Sumber dibatalkan | konsumen berhenti di tengah → generator sumber benar-benar berhenti (blok `finally`-nya jalan) |
| Parser frame | unit test fungsi format: field `event`, JSON `data`, baris kosong pemisah |

Perintah verifikasi ditulis di README saat implementasi (`uv run pytest`, `uv run ruff check .`).

---

## 8. Failure mode

| Kegagalan | Gejala di client | Perilaku sistem | Deteksi |
| --- | --- | --- | --- |
| Client menutup koneksi di tengah stream | tidak ada | generator dibatalkan; kerja dihentikan (nanti: panggilan LLM dibatalkan) | log warning "client disconnected" |
| Exception di generator | stream berhenti | frame `error` dikirim, koneksi ditutup | frame terakhir bukan `done`; traceback di log server |
| Proxy/CDN buffering | token baru muncul sekaligus di akhir | header `X-Accel-Buffering: no` + heartbeat | uji lewat proxy, bandingkan dengan `curl -N` langsung |
| Provider/LLM lambat (task 5) | layar diam lama | heartbeat menjaga koneksi tetap hidup | ada `: ping` di stream mentah |
| Server restart | koneksi putus | tidak ada resume (di luar cakupan) | client harus retry manual |

---

## 9. Acceptance criteria

- [ ] `uv sync` lalu `uv run uvicorn app.main:app --reload` berjalan tanpa error
- [ ] `POST /api/chat/stream` mengeluarkan token bertahap, terlihat di `/demo` dan `curl -N`
- [ ] Disconnect (tombol Stop / Ctrl+C) tercatat di log server, bukan crash
- [ ] `uv run pytest` hijau, `uv run ruff check .` bersih
- [ ] `docs/learning/fastapi-async-sse.md` + index `docs/README.md` diperbarui
- [ ] `.gitignore` mencakup artefak Python (`.venv/`, `__pycache__/`, cache test/ruff)
- [ ] Tidak ada secret di repo (`.env` di-ignore, `.env.example` memakai placeholder)
- [ ] Bagian *Lingkungan* di `AGENTS.md` diperbarui (Python + Node)
