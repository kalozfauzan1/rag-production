# Log Keputusan (ADR ringkas)

Format: **tanggal · keputusan · konteks/kenapa · alternatif yang ditolak · konsekuensi**.
Satu entri ditulis saat keputusan diambil, bukan setelahnya.

---

## 2026-09-18 — Task 1: fondasi backend (FastAPI + SSE)

### D1. Dependency manager: uv

- **Konteks:** project baru, banyak dependency akan menyusul (fastapi, httpx, tiktoken, qdrant/supabase, dst). Python default di mesin (3.10.6) terlalu tua untuk dipakai langsung.
- **Keputusan:** uv 0.11.6 (sudah terpasang), dengan `uv.lock` di-commit.
- **Alternatif ditolak:** pip+venv (tanpa lockfile, lambat, interpreter harus diurus manual); poetry (lebih berat, tidak mengunduh interpreter sendiri).
- **Konsekuensi:** semua perintah memakai `uv run …` / `uv sync`; kontributor wajib punya uv; deploy nanti bisa memakai image resmi uv.

### D2. Versi Python: 3.13

- **Konteks:** 3.14 sudah terpasang di mesin; task 3–4 akan menyentuh wheel native (torch untuk BGE-m3, tiktoken, qdrant-client).
- **Keputusan:** pin 3.13 lewat `.python-version`; uv mengunduh interpreter-nya sendiri.
- **Alternatif ditolak:** 3.10 system (terlalu tua, banyak fitur typing/asyncio modern hilang); 3.14 (lebih baru, tapi risiko wheel native belum tersedia lebih tinggi dan tanpa manfaat yang kita butuhkan sekarang).
- **Konsekuensi:** ganti versi nanti cukup `uv python pin <versi>` + `uv sync`; tim/CI harus ikut membaca `.python-version`.

### D3. SSE ditulis manual, bukan `sse-starlette`

- **Konteks:** task ini bertujuan memahami mekanisme, bukan sekadar punya endpoint jalan.
- **Keputusan:** `StreamingResponse` + format frame manual; heartbeat, error, dan cancellation ditulis sendiri di `app/core/sse.py`.
- **Alternatif ditolak:** `sse-starlette` sejak awal (wire format, ping, disconnect jadi kotak hitam).
- **Konsekuensi:** kita memelihara sendiri detail protokol; `sse-starlette` tetap dicatat sebagai pembanding produksi dan bisa dipakai di task berikutnya setelah mekanismenya dipahami.

### D4. Struktur repo: FastAPI di root, `web/` menyusul

- **Konteks:** akan ada dua service (FastAPI + Next.js) dan dua target deploy (Railway/Fly + Vercel).
- **Keputusan:** paket `app/` + `tests/` + `pyproject.toml` di root; Next.js masuk ke `web/` di task 7.
- **Alternatif ditolak:** `api/` + `web/` sejak awal (lebih rapi, tapi menambah friksi path untuk semua perintah sekarang tanpa manfaat langsung).
- **Konsekuensi:** Vercel nanti diarahkan ke root-directory `web/`; Railway/Fly memakai root repo.

### D5. Test: pytest + pytest-asyncio + httpx AsyncClient

- **Konteks:** endpoint yang diuji memakai streaming async; `TestClient` bawaan Starlette bersifat sinkron.
- **Keputusan:** `pytest-asyncio` mode `auto` + `httpx.AsyncClient` + `ASGITransport`, stream dibaca via `client.stream(...)`.
- **Alternatif ditolak:** `TestClient` sinkron (kurang merepresentasikan client nyata); menambah `pytest-httpx`/mock server (belum ada dependency eksternal yang perlu dimock).
- **Konsekuensi:** test ditulis `async def` tanpa marker (mode auto); override dependency lewat `app.dependency_overrides`.

### D6. Lint & format: ruff

- **Konteks:** butuh lint + format konsisten tanpa konfigurasi berlapis.
- **Keputusan:** ruff (check + format), konfigurasi di `pyproject.toml`.
- **Alternatif ditolak:** black + flake8 + isort (tiga tool, lebih lambat, konfigurasi tersebar).
- **Konsekuensi:** satu perintah `uv run ruff check .` / `uv run ruff format .`; aturan dipilih selektif (E, F, I, UP, B, ASYNC), bukan semuanya.

### D7. Gaya dependency FastAPI: `Annotated[..., Depends(...)]`

- **Konteks:** ruff (aturan `B008` dari flake8-bugbear) menandai `Depends(...)` yang ditulis sebagai nilai default argumen. Dua jalan keluar: mengecualikan `fastapi.Depends` di konfigurasi, atau memakai bentuk `Annotated`.
- **Keputusan:** pakai `Annotated[Streamer, Depends(get_streamer)]` — bentuk yang sekarang direkomendasikan dokumentasi FastAPI.
- **Alternatif ditolak:** `= Depends(...)` + `extend-immutable-calls` (menambah pengecualian lint untuk pola yang memang sudah usang).
- **Konsekuensi:** semua dependency di task berikutnya memakai `Annotated`; tidak ada pengecualian lint di `pyproject.toml`.
