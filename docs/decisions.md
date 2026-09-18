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
- **Konsekuensi:** satu perintah `uv run ruff check .` / `uv run ruff format .`; aturan dipilih selektif (E, F, I, UP, B, ASYNC), bukan semuanya. File Markdown dikecualikan dari formatter (`extend-exclude`), karena ruff ikut memformat blok kode Python di dokumen — dan contoh di dokumen sengaja ditulis untuk dijelaskan, bukan untuk dijalankan.

### D7. Gaya dependency FastAPI: `Annotated[..., Depends(...)]`

- **Konteks:** ruff (aturan `B008` dari flake8-bugbear) menandai `Depends(...)` yang ditulis sebagai nilai default argumen. Dua jalan keluar: mengecualikan `fastapi.Depends` di konfigurasi, atau memakai bentuk `Annotated`.
- **Keputusan:** pakai `Annotated[Streamer, Depends(get_streamer)]` — bentuk yang sekarang direkomendasikan dokumentasi FastAPI.
- **Alternatif ditolak:** `= Depends(...)` + `extend-immutable-calls` (menambah pengecualian lint untuk pola yang memang sudah usang).
- **Konsekuensi:** semua dependency di task berikutnya memakai `Annotated`; tidak ada pengecualian lint di `pyproject.toml`.

### D8. Logging aplikasi dikonfigurasi eksplisit; pesan log ASCII

- **Konteks:** ditemukan saat verifikasi manual — uvicorn hanya mengatur logger `uvicorn.*`, root logger tanpa handler, sehingga `logger.info(...)` dari kode kita tidak muncul sama sekali (pesan disconnect hilang). Temuan kedua: em-dash di pesan log rusak (`�`) ketika stderr dialihkan ke file di Windows, karena Python memakai encoding locale, bukan UTF-8.
- **Keputusan:** `logging.basicConfig(level=INFO)` dipanggil di `create_app()`; pesan log ditulis ASCII (body response HTTP tetap UTF-8, tidak terpengaruh).
- **Alternatif ditolak:** menaikkan level log ke WARNING agar muncul lewat handler terakhir (menyembunyikan informasi, bukan mengonfigurasi); membiarkan encoding locale (hasilnya rusak di file log).
- **Konsekuensi:** log aplikasi terlihat di dev maupun saat deploy; aturan "ASCII untuk pesan log" berlaku untuk kode berikutnya.

---

## 2026-09-18 — Task 2: ingestion & chunking

### D9. Parser PDF: pdfplumber

- **Konteks:** perlu mengekstrak teks PDF untuk chunking; pilihan ini menentukan lisensi dan kualitas teks.
- **Keputusan:** pdfplumber (MIT).
- **Alternatif ditolak:** PyMuPDF (jauh lebih cepat tapi AGPL-3.0 — demo publik di task 8 bisa memicu kewajiban membuka kode); pypdfium2 (cepat dan longgar, tapi bantuan layout lebih sedikit, relevan untuk PDF dua kolom); pypdf (ekstraksi paling dasar, urutan teks acak).
- **Konsekuensi:** parsing lebih lambat; kalau nanti jadi masalah nyata, jalur gantinya PyMuPDF dengan konsekuensi lisensi — dicatat, bukan diputuskan sekarang.

### D10. Ekstraksi HTML: trafilatura

- **Konteks:** HTML perlu dibersihkan dari boilerplate (menu, iklan, footer) sebelum di-chunk.
- **Keputusan:** trafilatura (Apache-2.0), output markdown supaya heading bisa jadi metadata section.
- **Alternatif ditolak:** readability-lxml (lebih sederhana, hasil kurang rapi di halaman non-artikel); heuristik BeautifulSoup sendiri (rapuh dan memakan waktu untuk masalah yang bukan inti pembelajaran).
- **Konsekuensi:** satu dependency besar; heuristik pembersihannya tidak kita tulis sendiri — sebagai gantinya kita bandingkan hasilnya dengan `get_text()` mentah di dokumen learning.

### D11. Pemrosesan ingestion: in-process + thread pool

- **Konteks:** parsing sinkron dan CPU-bound; endpoint upload tidak boleh menggantung menunggu selesai.
- **Keputusan:** job in-process (`asyncio.create_task` + registry) dengan pekerjaan berat dijalankan lewat `asyncio.to_thread`; status dibaca dari `meta.json` + registry.
- **Alternatif ditolak:** `BackgroundTasks` bawaan Starlette (terikat siklus response, kurang cocok untuk job panjang); queue Redis/Celery (menambah layanan yang harus di-deploy, padahal masalahnya belum ada).
- **Konsekuensi:** job hilang saat restart — dimitigasi dengan rekonsiliasi saat startup (status `processing` yatim diubah jadi `failed`). Jalur peningkatan ke queue dicatat sebagai utang task 9.

### D12. Satuan chunk: token `cl100k_base` (tiktoken)

- **Konteks:** roadmap meminta 500–800 token; "token" harus didefinisikan karena tiap model punya tokenizer berbeda.
- **Keputusan:** tiktoken `cl100k_base` — tokenizer yang dipakai `text-embedding-3-*` (kandidat utama task 3); panjang chunk tetap dibatasi token, bukan karakter.
- **Alternatif ditolak:** menghitung karakter (tidak mencerminkan batas model embedding/konteks); memakai tokenizer model embedding sejak awal (modelnya belum dipilih — akan mengunci keputusan task 3 lebih awal).
- **Konsekuensi:** kalau task 3 memilih Voyage atau BGE-m3, jumlah token untuk teks Indonesia bisa berbeda jauh (1,5–2×); risiko ini dicatat di spec dan akan diukur di task 3.

### D13. Penyimpanan hasil: file JSONL di `data/`

- **Konteks:** hasil ingestion harus bisa dipakai task 3 (embedding) dan diperiksa manual.
- **Keputusan:** `data/uploads/{sha256}.{ext}`, `data/documents/{doc_id}/meta.json`, `chunks.jsonl`.
- **Alternatif ditolak:** SQLite (skema yang akan digantikan vector DB di task 4, plus tidak bisa dibaca mata); menyimpan di memori (hilang saat restart, tidak bisa diperiksa).
- **Konsekuensi:** `data/` masuk `.gitignore`; `doc_id` = SHA-256 isi file sehingga upload ulang bersifat idempotent dan nama file dari client tidak pernah dipakai sebagai path.

### D14. Hasil ekstraksi berupa blocks, bukan satu string panjang

- **Konteks:** sitasi task 5 membutuhkan asal-usul teks (halaman PDF, section HTML/Markdown).
- **Keputusan:** extractor mengembalikan `ExtractedDocument` berisi `Block(text, order, page, section)`; chunker bekerja di atas blocks dan mewarisi metadata itu.
- **Alternatif ditolak:** teks tunggal + chunk tanpa metadata (lebih cepat, tapi sitasi nanti hanya bisa menyebut "chunk 37" tanpa lokasi asli).
- **Konsekuensi:** setiap extractor punya tanggung jawab tambahan memetakan struktur dokumen; diuji per format.

### D15. Batas chunk ditentukan dari offset karakter, bukan penjumlahan token per potongan

- **Konteks:** implementasi pertama memecah teks secara rekursif per separator menjadi potongan kecil, lalu menjumlahkan token tiap potongan untuk mengisi anggaran. Hasil pengukuran: chunk hanya ~234 token padahal anggarannya 704. Sebabnya, tokenisasi BPE **tidak aditif** — `count_tokens("kata ")` sendirian ≈ 3 token, tetapi kontribusinya di dalam teks panjang ≈ 1 token, karena BPE menggabungkan pasangan yang sering muncul bersama.
- **Keputusan:** dokumen dijadikan satu teks; batas tiap chunk dicari sebagai offset karakter dengan `count_tokens` pada slice aslinya (binary search, diperkirakan dari rasio karakter/token), lalu digeser ke separator terdekat yang masih masuk 40% terakhir rentang.
- **Alternatif ditolak:** menghitung token per potongan lalu menjumlahkan (terbukti salah, chunk jadi 1/3 ukuran yang diminta); memakai jumlah karakter saja (tidak mencerminkan batas model embedding).
- **Konsekuensi:** algoritma lebih sederhana (tidak ada `_Piece`, `_split_recursive`, maupun `_force_split`); biaya tambahan berupa beberapa panggilan `count_tokens` per chunk untuk binary search. Pelajaran umumnya dicatat di dokumen learning: **jangan menjumlahkan hasil tokenizer secara parsial**.
