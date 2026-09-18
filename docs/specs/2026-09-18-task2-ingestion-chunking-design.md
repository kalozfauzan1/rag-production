# Task 2 — Ingestion (PDF/HTML/Markdown) + Recursive Chunking

- **Tanggal:** 2026-09-18
- **Status:** draft — menunggu review
- **Posisi:** task 2 dari 9 (roadmap belajar di `AGENTS.md`)

---

## 1. Tujuan & batas

Mengubah file dokumen menjadi **chunk** yang siap di-embed di task 3, lengkap dengan metadata
yang cukup untuk sitasi di task 5, dan bisa dipicu lewat HTTP (upload).

**Termasuk:**

- Upload via `POST /api/documents` (multipart), status via `GET /api/documents/{id}`.
- Ekstraksi PDF (teks digital), HTML, Markdown/TXT.
- Normalisasi teks, pemotongan **recursive** berbasis token (500–800 token, overlap ~12%).
- Metadata per chunk: halaman/section, posisi karakter, jumlah token.
- Penyimpanan hasil ke disk (JSONL) supaya bisa diperiksa mata dan dipakai task berikutnya.

**Sengaja belum dikerjakan:**

- **OCR** — PDF hasil scan ditolak dengan pesan jelas (bukan menghasilkan teks kosong).
- DOCX, EPUB, dan format lain.
- Embedding & vector DB → task 3–4.
- Queue eksternal (Redis/Celery) → ditunda sampai restart-loss jadi masalah nyata.
- Live progress via SSE → mesinnya sudah ada di task 1, ditambahkan kalau UI butuh.

---

## 2. Keputusan

Detail ADR ada di [`docs/decisions.md`](../decisions.md) (D9–D14).

| # | Keputusan | Pilihan | Alasan singkat |
| --- | --- | --- | --- |
| D9 | Parser PDF | **pdfplumber** | MIT, akses char/word/posisi (bagus untuk belajar); lambat tapi belum jadi masalah |
| D10 | Ekstraksi HTML | **trafilatura** | khusus artikel, membuang boilerplate dengan skor kepadatan teks; +1 eksperimen pembanding vs `BeautifulSoup.get_text()` |
| D11 | Pemrosesan | **in-process** (`asyncio.create_task` + registry) + `asyncio.to_thread` | tanpa infra; parsing CPU-bound tidak boleh memblokir event loop |
| D12 | Satuan chunk | **token** (`tiktoken`, `cl100k_base`) | cocok dengan `text-embedding-3-*`; ketidakportabelan antar-model dicatat sebagai risiko |
| D13 | Penyimpanan | file di `data/` + `meta.json` + `chunks.jsonl` | gampang diintip, jadi input task 3–4; SQLite belum perlu karena akan digantikan vector DB |
| D14 | Struktur hasil ekstraksi | **blocks** (teks + halaman/section) | sitasi task 5 butuh asal-usul, bukan cuma teks panjang |

---

## 3. Arsitektur & alur data

```text
POST /api/documents (multipart file)
   │  validasi: ekstensi, ukuran, magic bytes PDF, sha256 → doc_id
   ▼
data/uploads/{doc_id}.{ext}          ← file asli, nama dari client tidak pernah jadi path
   │  JobRunner.create_task(...)      ← in-process, status di registry + meta.json
   ▼  (respons 202 langsung dikirim, tidak menunggu proses selesai)
asyncio.to_thread(pipeline.ingest_file)
   │
   ├─ 1. extract   pilih extractor dari ekstensi → pdfplumber / trafilatura / text
   │               hasil: ExtractedDocument { blocks, page_count, title, metadata }
   ├─ 2. normalize rapikan teks per block (hyphen pecah baris, spasi, baris kosong)
   ├─ 3. chunk     recursive split per block → pack sampai budget → overlap
   │               hasil: list[Chunk] dengan page/section/char range/token_count
   └─ 4. persist   data/documents/{doc_id}/meta.json + chunks.jsonl
   ▼
GET /api/documents/{id}   → status: queued | processing | completed | failed
GET /api/documents        → daftar
GET /api/documents/{id}/chunks → isi chunk (untuk diperiksa)
```

**Kenapa parsing di thread pool:** pdfplumber dan trafilatura sinkron dan CPU-bound. Kalau
dijalankan langsung di event loop, semua koneksi SSE dari task 1 ikut berhenti (termasuk
`: ping`). Ini akan diukur, bukan diasumsikan — lihat §10 eksperimen.

---

## 4. Kontrak API

### 4.1 `POST /api/documents`

`multipart/form-data`, field `file`.

| Kondisi | Status | Body |
| --- | --- | --- |
| Diterima, diproses | `202` | `{document_id, filename, size_bytes, status: "queued", duplicate: false}` + header `Location: /api/documents/{id}` |
| Isi file sama, dokumennya `completed` / masih `queued` / `processing` | `200` | metadata yang ada + `duplicate: true`; tidak ada job kedua |
| Isi file sama, tapi dokumen sebelumnya `failed` | `202` | diproses ulang (retry): status kembali `queued`, `duplicate: false` |
| Ekstensi/tipe tidak didukung | `415` | `{detail: "..."}` |
| File melebihi batas | `413` | `{detail: "..."}` |
| Field `file` tidak ada | `422` | format error FastAPI |

Ekstensi yang diterima: `.pdf`, `.html`, `.htm`, `.md`, `.markdown`, `.txt`.
Batas ukuran default 20 MB (`MAX_UPLOAD_BYTES`).

### 4.2 `GET /api/documents/{document_id}`

```json
{
  "document_id": "9f2c…",
  "filename": "laporan.pdf",
  "status": "processing",
  "stage": "extracting",
  "progress": 0.42,
  "chunk_count": null,
  "page_count": 12,
  "error": null
}
```

`stage`: `storing | extracting | normalizing | chunking | persisting | completed | failed`.
`progress`: 0–1 bila bisa dihitung (jumlah halaman selesai), `null` bila tidak.

### 4.3 `GET /api/documents`

Daftar dokumen (id, filename, status, chunk_count, created_at). Diurutkan terbaru dulu.

### 4.4 `GET /api/documents/{document_id}/chunks?offset=0&limit=20`

Isi chunk untuk pemeriksaan manual dan (nanti) untuk menampilkan sumber di UI.

---

## 5. Model data

```python
class Block(BaseModel):
    """Satu potongan teks beserta asal-usulnya."""
    text: str
    order: int                 # urutan dalam dokumen
    page: int | None = None    # 1-based, hanya PDF
    section: str | None = None # heading terdekat, hanya HTML/Markdown

class ExtractedDocument(BaseModel):
    blocks: list[Block]
    page_count: int | None = None
    title: str | None = None

class Chunk(BaseModel):
    doc_id: str
    chunk_index: int
    text: str
    token_count: int
    char_start: int            # offset di teks dokumen ternormalisasi
    char_end: int
    page: int | None = None    # halaman tempat konten baru chunk dimulai
    section: str | None = None

class DocumentMeta(BaseModel):
    doc_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: Literal["queued", "processing", "completed", "failed"]
    stage: str | None
    created_at: datetime
    updated_at: datetime
    page_count: int | None = None
    block_count: int | None = None
    chunk_count: int | None = None
    title: str | None = None
    error: str | None = None
```

### Tata letak disk

```text
data/
├── uploads/{doc_id}.{ext}                 # file asli
└── documents/{doc_id}/
    ├── meta.json                          # DocumentMeta
    └── chunks.jsonl                       # satu Chunk per baris
```

`doc_id` = SHA-256 isi file (content-addressed). Upload ulang file yang sama = idempotent,
dan namanya tidak bisa dipakai untuk keluar dari direktori `data/`.

---

## 6. Ekstraksi per format

| Format | Cara | Menghasilkan |
| --- | --- | --- |
| PDF | pdfplumber, per halaman → pecah jadi paragraf (baris kosong) | blocks dengan `page`, `page_count` |
| HTML | trafilatura (`output_format="markdown"`) → heading jadi `section` | blocks dengan `section`, `title` dari `<title>` |
| MD/TXT | baca teks, heading (`#`) jadi `section`, paragraf jadi block | blocks dengan `section` |

Aturan yang berlaku untuk semua format:

- **Normalisasi**: gabungkan kata yang terpotong hyphen di akhir baris (`infor-\nmation` → `information`), rapikan spasi ganda, jadikan 3+ baris kosong menjadi satu pemisah paragraf.
- **PDF tanpa text layer** (hasil scan): kalau rata-rata teks < 50 karakter per halaman → gagal dengan pesan `"PDF tidak punya lapisan teks (kemungkinan hasil scan); OCR belum didukung"`. Ini lebih jujur daripada menghasilkan dokumen kosong.
- **PDF terenkripsi / rusak**: error ditangkap, status `failed`, pesannya spesifik.
- Format markdown: sintaks inline (`**tebal**`, `_miring_`, `` `kode` ``) dibersihkan, teks link dipertahankan. Blok kode dibiarkan apa adanya (isi teknis tetap berharga untuk retrieval).

---

## 7. Algoritma chunking

Tiga tahap:

1. **Flatten** — semua block digabung menjadi satu teks ternormalisasi (pemisah `\n\n`); rentang tiap block dicatat, dan pergantian section ditandai sebagai **batas keras**.
2. **Cari batas tiap chunk** — dari posisi awal chunk, cari offset terjauh yang isinya masih ≤ `MAX_TOKENS - OVERLAP_TOKENS` token. Perhitungannya memakai `count_tokens` pada slice teks aslinya (binary search; titik awal diperkirakan dari rasio karakter/token dokumen). Batas akhir lalu digeser mundur ke separator paling semantik (`\n\n` → `\n` → `. ` → ` `) yang posisinya masih berada di 40% terakhir rentang, dan tidak pernah melewati batas section. Kalau sisa dokumen sudah muat dalam satu chunk, tidak ada pemotongan sama sekali.
3. **Overlap** — ekor chunk sebelumnya (≈ `OVERLAP_TOKENS`, utuh per kata) disalin ke depan chunk baru. Anggaran overlap dihitung **di dalam** `MAX_TOKENS`, jadi panjang chunk tetap ≤ 800.

**Kenapa tidak menjumlahkan token per potongan kecil:** tokenisasi BPE (*Byte Pair Encoding* — cara tokenizer memecah teks menjadi unit yang sering muncul bersama) **tidak aditif**. `count_tokens("kata ")` sendirian ≈ 3 token, tetapi di dalam teks panjang kontribusinya ≈ 1 token. Implementasi pertama — pecah teks secara rekursif lalu jumlahkan token tiap potongan — menghasilkan chunk 234 token padahal anggarannya 704. Terukur saat implementasi, bukan dugaan; karena itu batas chunk ditentukan dari `count_tokens` pada slice teks asli.

Angka default (config, bisa diubah lewat `.env`):

| Parameter | Default | Arti |
| --- | --- | --- |
| `CHUNK_MAX_TOKENS` | `800` | batas atas token per chunk (termasuk overlap) |
| `CHUNK_OVERLAP_TOKENS` | `96` | ≈12% dari maksimum |

**Chunk terakhir boleh lebih pendek** dari yang lain. Memaksanya masuk ke chunk sebelumnya
akan melewati `MAX_TOKENS`, dan chunk pendek tetap chunk yang sah. Perilaku ini diukur di
task 9 dan dicatat di dokumen learning; kalau ternyata mengganggu retrieval, penyeimbangan
ulang (memindahkan kata dari chunk sebelumnya) bisa ditambahkan — belum sekarang.

Atribusi metadata: `page`/`section` mengikuti **konten baru** chunk, bukan teks overlap yang
disalin dari chunk sebelumnya; `char_start` menunjuk ke awal konten baru. Alasannya: sitasi
harus menunjuk ke tempat teks itu benar-benar berada di dokumen asli.

**Risiko yang dicatat jujur:** "token" bergantung tokenizer. `cl100k_base` dipakai
`text-embedding-3-*`; kalau task 3 memilih Voyage atau BGE-m3 (tokenizer XLM-R), teks
Indonesia bisa menghasilkan token 1,5–2× lebih banyak sehingga "800 token" jadi lebih pendek
dari yang diharapkan. Kita ukur di task 3 dan sesuaikan kalau perlu.

---

## 8. Eksekusi background & status

- `JobRunner` (`app/core/jobs.py`): registry in-memory `{doc_id: JobState}` + `asyncio.create_task`.
  Referensi task disimpan (kalau tidak, task bisa di-GC dan job mati diam-diam).
- `JobRunner.wait(doc_id)` dipakai test supaya deterministik tanpa polling.
- Parsing dijalankan lewat `asyncio.to_thread` (sync library, CPU-bound).
- Status yang dilaporkan **dihitung saat dibaca**, bukan dipindai saat startup: kalau `meta.status` masih `queued`/`processing` tapi tidak ada job aktif untuk dokumen itu dan `updated_at`-nya lebih tua dari waktu proses ini mulai (`PROCESS_STARTED_AT`), status yang dilaporkan menjadi `failed` dengan pesan "Server restart saat dokumen sedang diproses". Alasan tidak memakai pemindaian saat startup: `create_app()` dipanggil saat import, sehingga test akan menyentuh `data/` milik dev — efek samping yang tidak diinginkan.
- Dokumen yang `failed` boleh diunggah ulang dan akan diproses lagi (retry), lihat §4.1.

---

## 9. Keamanan upload

| Ancaman | Penanganan |
| --- | --- |
| Path traversal (`../../etc/passwd`) | nama file dari client tidak pernah dipakai sebagai path; file disimpan sebagai `{sha256}.{ext}` dengan ext dari whitelist |
| File raksasa | batas ukuran dibaca bertahap dari stream, bukan setelah file utuh ada di memori |
| Tipe file dipalsukan | ekstensi diperiksa **dan** magic bytes PDF (`%PDF-`) untuk `.pdf` |
| Zip bomb / decompression | tidak relevan di task ini (tidak ada format arsip) |
| Isi berbahaya (JS di HTML) | HTML diperlakukan sebagai teks; tidak ada rendering |

---

## 10. Failure mode

| Kegagalan | Gejala ke pemanggil | Perilaku sistem | Deteksi |
| --- | --- | --- | --- |
| PDF hasil scan | status `failed`, pesan menyebut OCR | pipeline berhenti setelah ekstraksi | `meta.json` + `GET` status |
| PDF rusak/terenkripsi | status `failed` | error ditangkap, tidak ada file setengah jadi | pesan error spesifik |
| HTML tanpa isi artikel | `completed` dengan 0 chunk | block kosong tidak menghasilkan chunk | `chunk_count = 0` |
| Server restart saat memproses | status `failed` ("server restart") | rekonsiliasi saat startup | job registry kosong |
| Disk penuh / tidak bisa menulis | status `failed` | exception IO ditangkap di job | log + `meta.json` |
| Parser menggantung (file aneh) | status `processing` selamanya | belum ada timeout — **batasan yang diketahui** | dicatat sebagai utang task 9 |
| Event loop diblokir parsing | koneksi SSE lain tersendat | dicegah dengan `to_thread` | eksperimen jitter `: ping` |

---

## 11. Strategi test

| Berkas | Kasus |
| --- | --- |
| `tests/test_chunking.py` | budget token tidak terlampaui; overlap muncul di chunk berikutnya; section tidak menyatu dalam satu chunk; paragraf raksasa jatuh ke pemecahan kalimat; ekor pendek tetap jadi chunk sendiri; teks unicode utuh |
| `tests/test_normalize.py` | hyphen terpotong disambung; spasi ganda dirapikan; 3+ baris kosong jadi pemisah paragraf |
| `tests/test_extractors.py` | PDF: halaman & paragraf benar; PDF tanpa teks → error khusus; HTML: boilerplate (nav/footer) hilang, heading jadi section; Markdown: heading jadi section, sintaks inline dibersihkan |
| `tests/test_documents_api.py` | 202 + Location; duplicate → 200; ekstensi salah → 415; ukuran lebih → 413; alur status sampai `completed`; `chunks` endpoint; list dokumen |
| `tests/test_jobs.py` | `wait()` menunggu selesai; rekonsiliasi startup mengubah `processing` yatim jadi `failed` |

Fixture PDF: dibuat tanpa meng-commit biner — file PDF minimal ditulis sendiri oleh helper di
`tests/` (struktur PDF + xref dihitung saat menulis). Kalau pdfplumber ternyata tidak bisa
membacanya, cadangannya adalah `reportlab` sebagai dev-dependency (dicatat saat implementasi).

---

## 12. Acceptance criteria

- [ ] `uv run pytest` hijau; `uv run ruff check .` dan `ruff format --check .` bersih
- [ ] Upload PDF nyata (teks digital) → `completed` dengan chunk yang wajar (isi bisa dibaca di `chunks.jsonl`)
- [ ] Upload HTML dengan menu/iklan → boilerplate tidak ikut masuk chunk
- [ ] PDF hasil scan → `failed` dengan pesan yang menyebut OCR
- [ ] Upload ulang file yang sama → `200 duplicate`, tidak diproses dua kali
- [ ] Selama ingestion PDF besar berjalan, stream `/api/chat/stream` tetap mengeluarkan `: ping` tepat waktu (bukti `to_thread` bekerja)
- [ ] `data/` masuk `.gitignore`; tidak ada file pengguna yang ter-commit
- [ ] `docs/learning/ingestion-chunking.md` ditulis + index `docs/README.md` diperbarui
- [ ] Keputusan baru (D9–D14) tercatat di `docs/decisions.md`
