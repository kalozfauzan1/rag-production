# Task 2 — Ingestion + Recursive Chunking: Implementation Plan

> **Untuk eksekutor:** kerjakan plan ini task demi task, jangan lompat. Setiap task punya
> siklus test sendiri dan berakhir commit. Jangan tandai selesai sebelum perintah
> verifikasinya benar-benar dijalankan dan hasilnya sesuai.

**Goal:** File (PDF teks / HTML / Markdown / TXT) yang di-upload lewat
`POST /api/documents` berubah menjadi chunk bertoken 500–800 dengan metadata halaman/section,
tersimpan di disk, dan statusnya bisa dipantau.

**Architecture:** Route hanya menangani HTTP (validasi + simpan file) dan menyerahkan
pekerjaan ke job in-process. Pipeline sinkron (extract → normalize → chunk → persist)
dijalankan di thread supaya event loop — dan koneksi SSE dari task 1 — tidak tersendat.

**Tech Stack:** pdfplumber (PDF), trafilatura (HTML), tiktoken (hitung token), Pydantic v2
(model data), pytest + httpx (test).

**Spec:** `docs/specs/2026-09-18-task2-ingestion-chunking-design.md`

## Global Constraints

- Semua perintah Python lewat `uv run …` / `uv add`; jangan pakai `python`/`pip` global.
- Dependensi baru: `pdfplumber`, `trafilatura`, `tiktoken` (versi di-pin oleh `uv.lock`).
- Angka default dari spec: `MAX_UPLOAD_BYTES=20971520`, `CHUNK_MAX_TOKENS=800`,
  `CHUNK_OVERLAP_TOKENS=96`.
- Komentar & docstring Bahasa Indonesia (menjelaskan *kenapa*); identifier Bahasa Inggris.
- Pesan log ASCII (aturan D8); body HTTP tetap UTF-8.
- Tidak ada biner besar di git: `data/` masuk `.gitignore`, fixture PDF dibuat saat test.
- Setiap commit memakai pesan konvensional + trailer co-author.
- Perintah shell ditulis untuk PowerShell (Windows).

## Peta file

| File | Tanggung jawab | Task |
| --- | --- | --- |
| `app/core/config.py` (modify) | tambah setelan data dir, batas upload, angka chunk | 1 |
| `app/schemas/documents.py` | `Block`, `ExtractedDocument`, `Chunk`, `DocumentMeta`, response API | 2 |
| `app/services/ingestion/normalize.py` | rapikan teks hasil ekstraksi | 3 |
| `app/core/tokens.py` | hitung token + ambil ekor teks | 4 |
| `app/core/chunking.py` | recursive split, pack, overlap, metadata chunk | 4 |
| `app/services/ingestion/errors.py` | error domain + artinya | 5 |
| `app/services/ingestion/markdown_blocks.py` | markdown → blocks (dipakai HTML & MD) | 5 |
| `app/services/ingestion/extractors/` | pdf.py, html.py, text.py, registry | 5 |
| `app/services/ingestion/store.py` | baca/tulis `meta.json` + `chunks.jsonl` | 6 |
| `app/services/ingestion/uploads.py` | alirkan upload ke disk, batas ukuran, sha256 | 6 |
| `app/core/jobs.py` | `JobRunner`, `resolve_status` | 7 |
| `app/services/ingestion/pipeline.py` | `ingest_file` (sync) + `run_ingestion` (async) | 7 |
| `app/api/routes/documents.py` | 4 endpoint dokumen | 8 |
| `app/api/deps.py`, `app/main.py` (modify) | wiring router + job runner | 8 |
| `tests/pdf_factory.py` | pembuat PDF minimal untuk fixture | 5 |

---

## Task 1: Dependency, config, dan `.gitignore`

**Files:**
- Modify: `app/core/config.py`, `.gitignore`, `pyproject.toml`/`uv.lock` (lewat `uv add`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: —
- Produces: `Settings.data_dir: Path`, `Settings.uploads_dir: Path`, `Settings.documents_dir: Path`, `Settings.max_upload_bytes: int`, `Settings.chunk_max_tokens: int`, `Settings.chunk_overlap_tokens: int`

- [ ] **Step 1: Pasang dependency**

```powershell
uv add pdfplumber trafilatura tiktoken
uv run python -c "import tiktoken; print(len(tiktoken.get_encoding('cl100k_base').encode('halo dunia')))"
```

Baris kedua mengunduh kosakata `cl100k_base` (~1,7 MB) ke cache; setelah itu `tiktoken`
bisa dipakai offline. Kalau output bukan angka, dependensinya belum siap.

- [ ] **Step 2: Tulis test yang gagal — `tests/test_config.py`**

```python
"""Test setelan ingestion di Settings."""

from pathlib import Path

from app.core.config import Settings


def test_defaults_match_spec() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_upload_bytes == 20 * 1024 * 1024
    assert settings.chunk_max_tokens == 800
    assert settings.chunk_overlap_tokens == 96


def test_env_overrides_chunk_budget(monkeypatch) -> None:
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "500")

    assert Settings(_env_file=None).chunk_max_tokens == 500


def test_derived_directories_follow_data_dir(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)

    assert settings.uploads_dir == tmp_path / "uploads"
    assert settings.documents_dir == tmp_path / "documents"
```

- [ ] **Step 3: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'max_upload_bytes'`.

- [ ] **Step 4: Tambahkan setelan ke `app/core/config.py`**

```python
"""Konfigurasi aplikasi dari environment / file .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Semua knob runtime; default-nya nilai dev yang aman."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_origins: str = "http://localhost:3000"
    fake_token_delay_ms: int = 60
    sse_ping_interval_seconds: float = 15.0

    data_dir: Path = Path("data")
    max_upload_bytes: int = 20 * 1024 * 1024
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 96

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS boleh berisi beberapa origin, dipisah koma."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def uploads_dir(self) -> Path:
        """File asli hasil upload."""
        return self.data_dir / "uploads"

    @property
    def documents_dir(self) -> Path:
        """Metadata + chunk hasil ingestion."""
        return self.data_dir / "documents"


@lru_cache
def get_settings() -> Settings:
    """Dibaca sekali per proses; di test di-override lewat dependency_overrides."""
    return Settings()
```

- [ ] **Step 5: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Tambahkan `data/` ke `.gitignore`**

Tambahkan di akhir `.gitignore`:

```gitignore
# Data ingestion (file pengguna, bukan bagian dari repo)
data/
```

- [ ] **Step 7: Catat setelan baru di `.env.example`**

Tambahkan:

```dotenv
# Batas ukuran upload (byte)
MAX_UPLOAD_BYTES=20971520
# Angka chunking: batas token per chunk dan besar overlap antar-chunk
CHUNK_MAX_TOKENS=800
CHUNK_OVERLAP_TOKENS=96
```

- [ ] **Step 8: Commit**

```powershell
git add pyproject.toml uv.lock app/core/config.py tests/test_config.py .gitignore .env.example
@'
feat: add ingestion settings and dependencies

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 2: Model data dokumen

**Files:**
- Create: `app/schemas/documents.py`
- Test: `tests/test_document_schemas.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `Block(text: str, order: int, page: int | None, section: str | None)`
  - `ExtractedDocument(blocks: list[Block], page_count: int | None, title: str | None)`
  - `Chunk(doc_id, chunk_index, text, token_count, char_start, char_end, page, section)`
  - `DocumentMeta(doc_id, filename, content_type, size_bytes, sha256, status, stage, created_at, updated_at, page_count, block_count, chunk_count, title, error)`
  - `DocumentStatus = Literal["queued", "processing", "completed", "failed"]`
  - `DocumentUploadResponse`, `DocumentStatusResponse`, `DocumentListResponse`, `ChunkListResponse`

- [ ] **Step 1: Tulis test yang gagal — `tests/test_document_schemas.py`**

```python
"""Test model data ingestion."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.documents import Block, Chunk, DocumentMeta, ExtractedDocument


def test_chunk_survives_json_round_trip() -> None:
    chunk = Chunk(
        doc_id="abc123",
        chunk_index=0,
        text="Halo dunia",
        token_count=3,
        char_start=0,
        char_end=10,
        page=1,
        section="Bab Satu",
    )

    assert Chunk.model_validate_json(chunk.model_dump_json()) == chunk


def test_chunk_defaults_have_no_page_or_section() -> None:
    chunk = Chunk(doc_id="abc", chunk_index=1, text="x", token_count=1, char_start=0, char_end=1)

    assert chunk.page is None
    assert chunk.section is None


def test_document_status_rejects_unknown_value() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        DocumentMeta(
            doc_id="abc",
            filename="a.md",
            content_type="text/markdown",
            size_bytes=10,
            sha256="abc",
            status="selesai",
            created_at=now,
            updated_at=now,
        )


def test_meta_optional_fields_start_empty() -> None:
    now = datetime.now(UTC)
    meta = DocumentMeta(
        doc_id="abc",
        filename="a.md",
        content_type="text/markdown",
        size_bytes=10,
        sha256="abc",
        status="queued",
        created_at=now,
        updated_at=now,
    )

    assert (meta.page_count, meta.block_count, meta.chunk_count) == (None, None, None)
    assert (meta.stage, meta.title, meta.error) == (None, None, None)


def test_extracted_document_allows_zero_blocks() -> None:
    document = ExtractedDocument(blocks=[], page_count=1, title=None)
    assert document.blocks == []


def test_block_keeps_page_and_section() -> None:
    block = Block(text="isi", order=2, page=3, section="Lampiran")
    assert (block.order, block.page, block.section) == (2, 3, "Lampiran")
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_document_schemas.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.documents'`.

- [ ] **Step 3: Implementasi `app/schemas/documents.py`**

```python
"""Kontrak data untuk ingestion dokumen."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentStatus = Literal["queued", "processing", "completed", "failed"]


class Block(BaseModel):
    """Satu potongan teks beserta asal-usulnya di dokumen asli."""

    text: str
    order: int
    page: int | None = None
    section: str | None = None


class ExtractedDocument(BaseModel):
    """Hasil ekstraksi satu file, sebelum dinormalisasi dan dipotong."""

    blocks: list[Block] = Field(default_factory=list)
    page_count: int | None = None
    title: str | None = None


class Chunk(BaseModel):
    """Potongan siap di-embed; metadata-nya dipakai untuk sitasi di task 5.

    `char_start`/`char_end` menunjuk ke rentang **konten baru** di teks dokumen
    ternormalisasi (bukan termasuk teks overlap yang disalin dari chunk sebelumnya).
    """

    doc_id: str
    chunk_index: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    page: int | None = None
    section: str | None = None


class DocumentMeta(BaseModel):
    """Keadaan satu dokumen; disimpan sebagai `meta.json`."""

    doc_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    stage: str | None = None
    created_at: datetime
    updated_at: datetime
    page_count: int | None = None
    block_count: int | None = None
    chunk_count: int | None = None
    title: str | None = None
    error: str | None = None


class DocumentUploadResponse(BaseModel):
    """Jawaban `POST /api/documents`."""

    document_id: str
    filename: str
    size_bytes: int
    status: DocumentStatus
    duplicate: bool


class DocumentStatusResponse(DocumentMeta):
    """`meta.json` + progres dari job yang sedang berjalan (kalau ada)."""

    progress: float | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentStatusResponse]


class ChunkListResponse(BaseModel):
    document_id: str
    total: int
    offset: int
    limit: int
    chunks: list[Chunk]
```

- [ ] **Step 4: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_document_schemas.py -v
uv run ruff check .
```

Expected: 6 passed, ruff bersih.

- [ ] **Step 5: Commit**

```powershell
git add app/schemas/documents.py tests/test_document_schemas.py
@'
feat: add document ingestion schemas

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 3: Normalisasi teks

**Files:**
- Create: `app/services/ingestion/__init__.py` (kosong), `app/services/ingestion/normalize.py`
- Test: `tests/test_normalize.py`

**Interfaces:**
- Consumes: —
- Produces: `normalize_text(text: str) -> str`, `split_paragraphs(text: str) -> list[str]`

- [ ] **Step 1: Tulis test yang gagal — `tests/test_normalize.py`**

```python
"""Test normalisasi teks hasil ekstraksi."""

from app.services.ingestion.normalize import normalize_text, split_paragraphs


def test_joins_words_split_by_hyphen_at_line_end() -> None:
    assert normalize_text("infor-\nmation penting") == "information penting"


def test_collapses_repeated_spaces() -> None:
    assert normalize_text("halo    dunia") == "halo dunia"


def test_collapses_three_or_more_blank_lines() -> None:
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_removes_trailing_spaces_at_line_end() -> None:
    assert normalize_text("baris satu   \nbaris dua") == "baris satu\nbaris dua"


def test_normalizes_windows_line_endings() -> None:
    assert normalize_text("a\r\nb") == "a\nb"


def test_split_paragraphs_drops_empty_ones() -> None:
    assert split_paragraphs("Paragraf satu.\n\n\n\nParagraf dua.\n") == [
        "Paragraf satu.",
        "Paragraf dua.",
    ]


def test_split_paragraphs_of_blank_text_is_empty() -> None:
    assert split_paragraphs("   \n\n  ") == []
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_normalize.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ingestion'`.

- [ ] **Step 3: Buat `app/services/ingestion/__init__.py` kosong, lalu implementasi `app/services/ingestion/normalize.py`**

```python
"""Normalisasi teks hasil ekstraksi.

Aturannya sengaja sedikit dan bisa diperiksa: tujuannya membuang artefak ekstraksi
(hyphen pecah baris, spasi ganda), bukan menulis ulang kalimat.
"""

import re

_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_REPEATED_SPACES = re.compile(r"[ \t]{2,}")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Rapikan teks satu blok."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_LINEBREAK.sub(r"\1\2", text)
    text = _TRAILING_SPACES.sub("\n", text)
    text = _REPEATED_SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    """Pecah teks menjadi paragraf berdasarkan baris kosong."""
    normalized = normalize_text(text)
    return [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]
```

- [ ] **Step 4: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_normalize.py -v
uv run ruff check .
```

Expected: 7 passed, ruff bersih.

- [ ] **Step 5: Commit**

```powershell
git add app/services/ingestion tests/test_normalize.py
@'
feat: add text normalization for extracted documents

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 4: Tokenizer + chunker

**Files:**
- Create: `app/core/tokens.py`, `app/core/chunking.py`
- Test: `tests/test_tokens.py`, `tests/test_chunking.py`

**Interfaces:**
- Consumes: `Block`, `Chunk` (Task 2)
- Produces:
  - `count_tokens(text: str) -> int`
  - `tail_by_tokens(text: str, max_tokens: int) -> str`
  - `SEPARATORS: tuple[str, ...]`, `BLOCK_SEPARATOR = "\n\n"`
  - `chunk_document(blocks, *, doc_id, max_tokens=800, overlap_tokens=96) -> list[Chunk]`

> **Deviasi saat eksekusi (lihat D15):** kode `_Piece`/`_split_recursive`/`_force_split`/`_pack`
> di Step 7 tidak dipakai. Sebabnya terukur: tokenisasi BPE tidak aditif, sehingga menjumlahkan
> token per potongan kecil menghasilkan chunk ~234 token padahal anggarannya 704. Implementasi
> final memakai pencarian batas berbasis offset karakter dan ada di `app/core/chunking.py`.
> Test di Step 5 tetap berlaku tanpa perubahan.

- [ ] **Step 1: Tulis test yang gagal — `tests/test_tokens.py`**

```python
"""Test penghitung token."""

from app.core.tokens import count_tokens, tail_by_tokens


def test_empty_text_has_zero_tokens() -> None:
    assert count_tokens("") == 0


def test_longer_text_has_more_tokens() -> None:
    assert count_tokens("halo dunia") < count_tokens("halo dunia " * 20)


def test_special_token_literal_is_safe_to_count() -> None:
    # tiktoken melempar error untuk string yang menyerupai token spesial,
    # kecuali kalau disallowed_special dinonaktifkan.
    assert count_tokens("<|endoftext|>") > 0


def test_tail_returns_whole_words_from_the_end() -> None:
    text = "satu dua tiga empat lima enam tujuh delapan sembilan sepuluh"

    tail = tail_by_tokens(text, 6)

    assert text.endswith(tail)
    assert count_tokens(tail) <= 6


def test_tail_of_short_text_is_the_text_itself() -> None:
    assert tail_by_tokens("dua kata", 50) == "dua kata"


def test_tail_with_zero_budget_is_empty() -> None:
    assert tail_by_tokens("apa pun", 0) == ""
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_tokens.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.tokens'`.

- [ ] **Step 3: Implementasi `app/core/tokens.py`**

```python
"""Penghitung token berbasis tiktoken.

Tokenizer yang dipakai `cl100k_base` — sama dengan `text-embedding-3-*`, kandidat utama
task 3. Model embedding lain punya tokenizer berbeda, jadi angka "token" di sini tidak
otomatis berlaku untuk mereka (risiko yang dicatat di spec task 2).

Catatan operasional: `tiktoken.get_encoding()` mengunduh kosakata pada pemakaian pertama
(~1,7 MB) lalu menyimpannya di cache; setelah itu bisa dipakai offline.
"""

import tiktoken

_ENCODING_NAME = "cl100k_base"
_encoding: tiktoken.Encoding | None = None


def get_encoding() -> tiktoken.Encoding:
    """Encoding dipakai ulang; memuatnya butuh IO, jadi jangan per panggilan."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Jumlah token `cl100k_base` untuk teks ini."""
    if not text:
        return 0
    return len(get_encoding().encode(text, disallowed_special=()))


def tail_by_tokens(text: str, max_tokens: int) -> str:
    """Ambil ekor teks (utuh per kata) sebanyak maksimal `max_tokens` token.

    Dipakai untuk overlap antar-chunk. Bekerja per kata, bukan per potongan token,
    supaya tidak pernah memotong karakter di tengah — tiktoken akan menghasilkan
    U+FFFD untuk potongan byte yang tidak valid.
    """
    if max_tokens <= 0 or not text:
        return ""

    picked: list[str] = []
    used = 0
    for word in reversed(text.split()):
        cost = count_tokens(word) + (1 if picked else 0)  # +1 untuk spasi pemisah
        if used + cost > max_tokens:
            break
        picked.append(word)
        used += cost
    return " ".join(reversed(picked))
```

- [ ] **Step 4: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_tokens.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Tulis test yang gagal — `tests/test_chunking.py`**

```python
"""Test pemotongan dokumen menjadi chunk."""

from app.core.chunking import BLOCK_SEPARATOR, chunk_document
from app.core.tokens import count_tokens
from app.schemas.documents import Block


def make_text(tokens: int) -> str:
    """Teks yang panjangnya mendekati `tokens` token."""
    words: list[str] = []
    while count_tokens(" ".join(words)) < tokens:
        words.append("kata")
    return " ".join(words)


def make_blocks(*specs: tuple[str | None, int]) -> list[Block]:
    """(section, jumlah token) → daftar Block."""
    return [
        Block(text=make_text(tokens), order=index, section=section)
        for index, (section, tokens) in enumerate(specs)
    ]


def test_every_chunk_stays_within_max_tokens() -> None:
    blocks = make_blocks((None, 900), (None, 900), (None, 900))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) >= 2
    assert all(chunk.token_count <= 800 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_next_chunk_starts_with_tail_of_previous() -> None:
    blocks = make_blocks((None, 600), (None, 600))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) == 2
    previous_words = chunks[0].text.split()
    next_words = chunks[1].text.split()
    assert next_words[:5] == previous_words[-5:]


def test_chunks_do_not_cross_sections() -> None:
    # Dua section kecil: tanpa aturan batas section, keduanya akan jadi satu chunk.
    blocks = make_blocks(("Bab Satu", 200), ("Bab Dua", 200))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert [chunk.section for chunk in chunks] == ["Bab Satu", "Bab Dua"]


def test_giant_paragraph_is_split_at_sentence_boundaries() -> None:
    sentence = "Ini kalimat contoh yang cukup panjang. "
    text = sentence * 120
    blocks = [Block(text=text, order=0, section=None)]

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) >= 2
    assert all(chunk.token_count <= 800 for chunk in chunks)
    assert all(chunk.text.rstrip().endswith(".") for chunk in chunks)


def test_short_tail_stays_a_separate_chunk() -> None:
    # Dokumen lebih panjang dari budget: sisanya menjadi chunk pendek tersendiri.
    # Menggabungnya ke chunk sebelumnya akan melewati max_tokens, jadi tidak dilakukan.
    blocks = make_blocks((None, 750), (None, 200))

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert len(chunks) == 2
    assert all(chunk.token_count <= 800 for chunk in chunks)


def test_char_offsets_point_at_new_content() -> None:
    blocks = make_blocks((None, 600), (None, 600))
    document_text = BLOCK_SEPARATOR.join(block.text for block in blocks)

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    for chunk in chunks:
        assert document_text[chunk.char_start : chunk.char_end] in chunk.text


def test_unicode_text_is_not_mangled() -> None:
    blocks = [Block(text="Kafé Zürich 🎉 " * 80, order=0, section=None)]

    chunks = chunk_document(blocks, doc_id="d1", max_tokens=800, overlap_tokens=96)

    assert all("\ufffd" not in chunk.text for chunk in chunks)


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_document([], doc_id="d1") == []
```

- [ ] **Step 6: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_chunking.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.chunking'`.

- [ ] **Step 7: Implementasi `app/core/chunking.py`**

```python
"""Pemotongan dokumen menjadi chunk (recursive split) berbasis token.

Empat tahap: flatten → recursive split → pack → overlap. Tiap tahap bisa diuji
sendiri, dan urutannya penting: overlap ditambahkan paling akhir supaya panjang
chunk akhir tetap ≤ max_tokens.
"""

import re
from dataclasses import dataclass

from app.core.tokens import count_tokens, tail_by_tokens
from app.schemas.documents import Block, Chunk

# Dari yang paling semantik ke paling halus. String kosong = potong paksa.
SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")

# Pemisah antar block di teks dokumen ternormalisasi — dipakai juga saat
# menghitung offset karakter, jadi jangan diubah sepihak.
BLOCK_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class _Piece:
    """Potongan teks beserta lokasi dan asal-usulnya."""

    text: str
    start: int
    page: int | None
    section: str | None


def chunk_document(
    blocks: list[Block],
    *,
    doc_id: str,
    max_tokens: int = 800,
    overlap_tokens: int = 96,
) -> list[Chunk]:
    """Ubah block menjadi chunk ≤ max_tokens dengan overlap antar-chunk."""
    if not blocks:
        return []

    budget = max(1, max_tokens - overlap_tokens)
    pieces: list[_Piece] = []
    cursor = 0
    for block in blocks:
        for text, offset in _split_recursive(block.text, budget, SEPARATORS):
            pieces.append(
                _Piece(text=text, start=cursor + offset, page=block.page, section=block.section)
            )
        cursor += len(block.text) + len(BLOCK_SEPARATOR)

    chunks: list[Chunk] = []
    previous_text = ""
    for index, group in enumerate(_pack(pieces, budget=budget)):
        body = "".join(piece.text for piece in group)
        leading = len(body) - len(body.lstrip())
        body = body.strip()
        overlap = tail_by_tokens(previous_text, overlap_tokens) if index > 0 else ""
        text = f"{overlap}\n\n{body}" if overlap else body
        char_start = group[0].start + leading
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_index=index,
                text=text,
                token_count=count_tokens(text),
                char_start=char_start,
                char_end=char_start + len(body),
                page=group[0].page,
                section=group[0].section,
            )
        )
        previous_text = text
    return chunks


def _split_recursive(text: str, budget: int, separators: tuple[str, ...]) -> list[tuple[str, int]]:
    """Pecah `text` menjadi potongan ≤ budget token; hasilnya (teks, offset di dalam text).

    Memakai separator paling semantik lebih dulu; kalau satu potongan masih terlalu
    besar, pemecahan dilanjutkan dengan separator berikutnya.
    """
    if count_tokens(text) <= budget:
        return [(text, 0)]

    separator = separators[0] if separators else ""
    if not separator:
        return _force_split(text, budget)

    parts: list[tuple[str, int]] = []
    offset = 0
    # Lookbehind membuat separator tetap menempel di potongan sebelumnya, sehingga
    # penggabungan potongan mengembalikan teks asli persis (offset pun tetap sahih).
    for piece in re.split(f"(?<={re.escape(separator)})", text):
        if count_tokens(piece) <= budget:
            parts.append((piece, offset))
        else:
            parts.extend(
                (sub, offset + sub_offset)
                for sub, sub_offset in _split_recursive(piece, budget, separators[1:])
            )
        offset += len(piece)
    return parts


def _force_split(text: str, budget: int) -> list[tuple[str, int]]:
    """Potong paksa teks yang tidak punya separator (mis. blob tanpa spasi).

    Ukuran potongan diperkirakan dari rasio karakter→token, lalu diperbaiki
    berulang sampai semua potongan masuk budget.
    """
    pieces: list[tuple[str, int]] = [(text, 0)]
    while True:
        oversized = [(piece, start) for piece, start in pieces if count_tokens(piece) > budget]
        if not oversized:
            return pieces

        refined: list[tuple[str, int]] = []
        for piece, base in pieces:
            tokens = count_tokens(piece)
            if tokens <= budget:
                refined.append((piece, base))
                continue
            size = max(1, int(len(piece) * budget / tokens * 0.95))
            refined.extend(
                (piece[index : index + size], base + index)
                for index in range(0, len(piece), size)
            )
        pieces = refined


def _pack(pieces: list[_Piece], *, budget: int) -> list[list[_Piece]]:
    """Gabungkan potongan kecil menjadi grup ≤ budget; ganti section = potong paksa.

    Grup terakhir boleh lebih pendek dari yang lain: memaksanya masuk ke grup
    sebelumnya akan melewati `budget`, dan chunk pendek tetap chunk yang sah.
    """
    groups: list[list[_Piece]] = []
    current: list[_Piece] = []
    current_tokens = 0

    for piece in pieces:
        tokens = count_tokens(piece.text)
        changes_section = bool(current) and piece.section != current[-1].section
        if current and (changes_section or current_tokens + tokens > budget):
            groups.append(current)
            current = []
            current_tokens = 0
        current.append(piece)
        current_tokens += tokens

    if current:
        groups.append(current)

    return groups
```

- [ ] **Step 8: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_chunking.py -v
uv run ruff check .
```

Expected: 8 passed, ruff bersih. Kalau ada test yang gagal karena jumlah chunk tidak
sesuai dugaan, periksa dulu berapa token yang sebenarnya dihasilkan `make_text` — ukuran
chunk bergantung tokenizer, bukan jumlah kata. Sesuaikan angka di test, bukan aturan
chunking-nya.

- [ ] **Step 9: Commit**

```powershell
git add app/core/tokens.py app/core/chunking.py tests/test_tokens.py tests/test_chunking.py
@'
feat: add token counter and recursive chunker

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 5: Extractor per format

**Files:**
- Create: `app/services/ingestion/errors.py`, `app/services/ingestion/markdown_blocks.py`, `app/services/ingestion/extractors/__init__.py`, `base.py`, `pdf.py`, `html.py`, `text.py`
- Test: `tests/pdf_factory.py`, `tests/test_extractors.py`

**Interfaces:**
- Consumes: `Block`, `ExtractedDocument` (Task 2); `split_paragraphs` (Task 3)
- Produces:
  - `IngestionError`, `UnsupportedFormatError`, `InvalidFileError`, `UploadTooLargeError`, `ExtractionError`, `ScannedPdfError`
  - `markdown_to_blocks(markdown: str, *, page: int | None = None) -> list[Block]`
  - `Extractor` protocol, `ProgressCallback = Callable[[float], None]`
  - `EXTRACTORS: dict[str, Extractor]`, `SUPPORTED_EXTENSIONS: frozenset[str]`, `get_extractor(path: Path) -> Extractor`
  - `build_pdf(pages: list[str]) -> bytes` (helper test)

- [ ] **Step 1: Tulis helper fixture — `tests/pdf_factory.py`**

```python
"""Pembuat PDF minimal untuk test: tanpa dependency tambahan, tanpa biner di git.

Struktur: 1 catalog, 2 pages, 3 font, lalu per halaman: page object + content stream.
Tabel xref dihitung dari byte yang benar-benar ditulis, jadi PDF-nya valid.
"""


def build_pdf(pages: list[str]) -> bytes:
    """Setiap string di `pages` menjadi satu halaman berisi satu baris teks."""
    page_count = len(pages)
    first_page_object = 4
    first_content_object = first_page_object + page_count

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{first_page_object + i} 0 R' for i in range(page_count))}] "
            f"/Count {page_count} >>"
        ).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for index, page_text in enumerate(pages):
        stream = _content_stream(page_text)
        objects[first_page_object + index] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {first_content_object + index} 0 R >>"
        ).encode()
        objects[first_content_object + index] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    payload = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(payload)
        payload += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    size = max(objects) + 1
    xref_offset = len(payload)
    payload += f"xref\n0 {size}\n".encode()
    payload += b"0000000000 65535 f \n"
    for number in range(1, size):
        payload += f"{offsets[number]:010d} 00000 n \n".encode()
    payload += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return bytes(payload)


def _content_stream(page_text: str) -> bytes:
    escaped = page_text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
```

- [ ] **Step 2: Tulis test yang gagal — `tests/test_extractors.py`**

```python
"""Test extractor per format."""

from pathlib import Path

import pytest

from app.services.ingestion.errors import ScannedPdfError, UnsupportedFormatError
from app.services.ingestion.extractors import SUPPORTED_EXTENSIONS, get_extractor
from tests.pdf_factory import build_pdf

ARTICLE_HTML = """<!doctype html>
<html lang="id">
  <head><title>Panduan RAG</title></head>
  <body>
    <nav><a href="/">Beranda</a> | <a href="/tentang">Tentang</a></nav>
    <article>
      <h1>Panduan RAG</h1>
      <p>Isi artikel yang sebenarnya menjelaskan cara kerja retrieval augmented
      generation untuk pembaca yang baru mulai.</p>
      <p>Paragraf kedua menambahkan detail tentang chunking, embedding, dan
      bagaimana keduanya bertemu di tahap retrieval.</p>
      <p>Paragraf ketiga menutup dengan catatan tentang evaluasi kualitas
      jawaban supaya sistem tidak sekadar terlihat jalan.</p>
    </article>
    <footer>Hak cipta 2026</footer>
  </body>
</html>
"""


def test_pdf_extraction_keeps_page_numbers(tmp_path: Path) -> None:
    path = tmp_path / "dua-halaman.pdf"
    path.write_bytes(
        build_pdf(
            [
                "Halaman pertama berisi teks yang cukup panjang untuk diuji.",
                "Halaman kedua berisi teks yang berbeda dari halaman sebelumnya.",
            ]
        )
    )

    document = get_extractor(path)(path)

    assert document.page_count == 2
    assert {block.page for block in document.blocks} == {1, 2}
    assert "Halaman pertama" in " ".join(block.text for block in document.blocks)


def test_pdf_without_text_layer_is_reported_as_scanned(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(build_pdf([""]))

    with pytest.raises(ScannedPdfError):
        get_extractor(path)(path)


def test_html_extraction_drops_boilerplate(tmp_path: Path) -> None:
    path = tmp_path / "artikel.html"
    path.write_text(ARTICLE_HTML, encoding="utf-8")

    document = get_extractor(path)(path)
    text = " ".join(block.text for block in document.blocks)

    assert document.title == "Panduan RAG"
    assert "Isi artikel yang sebenarnya" in text
    assert "Beranda" not in text
    assert "Hak cipta" not in text


def test_markdown_headings_become_sections(tmp_path: Path) -> None:
    path = tmp_path / "catatan.md"
    path.write_text(
        "# Bab Satu\n\nIsi bab **pertama** dengan `kode`.\n\n## Sub Bab\n\nIsi sub bab.\n",
        encoding="utf-8",
    )

    document = get_extractor(path)(path)

    assert [block.section for block in document.blocks] == ["Bab Satu", "Sub Bab"]
    assert document.blocks[0].text == "Isi bab pertama dengan kode."


def test_plain_text_file_still_produces_blocks(tmp_path: Path) -> None:
    path = tmp_path / "catatan.txt"
    path.write_text("Paragraf satu.\n\nParagraf dua.\n", encoding="utf-8")

    document = get_extractor(path)(path)

    assert [block.text for block in document.blocks] == ["Paragraf satu.", "Paragraf dua."]


def test_unknown_extension_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedFormatError):
        get_extractor(tmp_path / "data.xlsx")

    assert ".pdf" in SUPPORTED_EXTENSIONS
```

- [ ] **Step 3: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_extractors.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ingestion.errors'`.

- [ ] **Step 4: Implementasi `app/services/ingestion/errors.py`**

```python
"""Error domain ingestion — dipetakan ke kode HTTP di lapisan API."""


class IngestionError(Exception):
    """Induk semua error ingestion."""


class UnsupportedFormatError(IngestionError):
    """Ekstensi file tidak punya extractor."""


class InvalidFileError(IngestionError):
    """Isi file tidak cocok dengan tipenya (mis. `.pdf` tanpa header `%PDF-`)."""


class UploadTooLargeError(IngestionError):
    """File melebihi batas `MAX_UPLOAD_BYTES`."""


class ExtractionError(IngestionError):
    """Gagal mengekstrak isi file (rusak, terenkripsi, dan sejenisnya)."""


class ScannedPdfError(ExtractionError):
    """PDF tidak punya lapisan teks — kemungkinan hasil scan; OCR belum didukung."""
```

- [ ] **Step 5: Implementasi `app/services/ingestion/markdown_blocks.py`**

```python
"""Ubah teks bergaya Markdown menjadi Block.

Dipakai dua tempat: file `.md`/`.txt` langsung, dan hasil HTML yang sudah
dibersihkan trafilatura (diminta dalam format markdown supaya heading-nya
bisa jadi metadata section).
"""

import re

from app.schemas.documents import Block

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"!\[(.*?)\]\((.*?)\)"), r"\1"),
    (re.compile(r"\[(.*?)\]\((.*?)\)"), r"\1"),
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"), r"\1"),
    (re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"), r"\1"),
    (re.compile(r"`(.+?)`"), r"\1"),
)


def markdown_to_blocks(markdown: str, *, page: int | None = None) -> list[Block]:
    """Heading jadi `section`; paragraf jadi block; isi blok kode dibiarkan utuh."""
    blocks: list[Block] = []
    section: str | None = None
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if text:
            blocks.append(Block(text=text, order=len(blocks), page=page, section=section))

    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        if not in_fence:
            heading = _HEADING.match(line)
            if heading:
                flush()
                section = heading.group(2).strip() or section
                continue
            if not line.strip():
                flush()
                continue
            buffer.append(_strip_inline(line))
            continue

        buffer.append(line)

    flush()
    return blocks


def _strip_inline(line: str) -> str:
    """Buang penanda inline (`**tebal**`, `` `kode` ``, link) supaya teks bersih."""
    for pattern, replacement in _INLINE_PATTERNS:
        line = pattern.sub(replacement, line)
    return line
```

- [ ] **Step 6: Implementasi `app/services/ingestion/extractors/base.py`**

```python
"""Kontrak extractor: file → ExtractedDocument.

Semua extractor **sinkron** dan dipanggil dari thread oleh pipeline, karena
pdfplumber dan trafilatura sinkron dan CPU-bound.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.schemas.documents import ExtractedDocument

ProgressCallback = Callable[[float], None]


class Extractor(Protocol):
    """Callable yang mengubah satu file menjadi block teks."""

    def __call__(
        self, path: Path, *, on_progress: ProgressCallback | None = None
    ) -> ExtractedDocument: ...
```

- [ ] **Step 7: Implementasi `app/services/ingestion/extractors/pdf.py`**

```python
"""Extractor PDF berbasis pdfplumber (teks digital, bukan hasil scan)."""

import logging
from pathlib import Path

import pdfplumber

from app.schemas.documents import Block, ExtractedDocument
from app.services.ingestion.errors import ExtractionError, ScannedPdfError
from app.services.ingestion.extractors.base import ProgressCallback
from app.services.ingestion.normalize import split_paragraphs

logger = logging.getLogger(__name__)

# Di bawah ini dianggap "tidak ada teks" — hampir pasti PDF hasil scan.
MIN_CHARS_PER_PAGE = 50


def extract_pdf(path: Path, *, on_progress: ProgressCallback | None = None) -> ExtractedDocument:
    """Baca PDF halaman per halaman; paragraf diambil dari pemisah baris kosong."""
    blocks: list[Block] = []
    total_chars = 0

    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                total_chars += len(text.strip())
                for paragraph in split_paragraphs(text):
                    blocks.append(Block(text=paragraph, order=len(blocks), page=index))
                if on_progress:
                    on_progress(index / page_count if page_count else 1.0)
    except Exception as exc:  # pdfplumber memakai beberapa tipe error (syntax, password, ...)
        logger.warning("Gagal membuka PDF %s: %s", path.name, exc)
        raise ExtractionError(f"Gagal membaca PDF: {exc}") from exc

    if page_count and total_chars / page_count < MIN_CHARS_PER_PAGE:
        raise ScannedPdfError(
            "PDF tidak punya lapisan teks (kemungkinan hasil scan); OCR belum didukung"
        )

    return ExtractedDocument(blocks=blocks, page_count=page_count)
```

- [ ] **Step 8: Implementasi `app/services/ingestion/extractors/html.py`**

```python
"""Extractor HTML: trafilatura membuang boilerplate, lalu diubah jadi block."""

import logging
import re
from pathlib import Path

import trafilatura

from app.schemas.documents import ExtractedDocument
from app.services.ingestion.errors import ExtractionError
from app.services.ingestion.extractors.base import ProgressCallback
from app.services.ingestion.markdown_blocks import markdown_to_blocks

logger = logging.getLogger(__name__)

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def extract_html(path: Path, *, on_progress: ProgressCallback | None = None) -> ExtractedDocument:
    """Ambil isi artikel; menu/iklan/footer dibuang oleh trafilatura."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        markdown = trafilatura.extract(
            raw,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
        )
    except Exception as exc:
        logger.warning("Gagal mengekstrak HTML %s: %s", path.name, exc)
        raise ExtractionError(f"Gagal mengekstrak HTML: {exc}") from exc

    if on_progress:
        on_progress(1.0)

    title = _title_of(raw)
    if not markdown:
        return ExtractedDocument(blocks=[], title=title)
    return ExtractedDocument(blocks=markdown_to_blocks(markdown), title=title)


def _title_of(html: str) -> str | None:
    match = _TITLE.search(html)
    return match.group(1).strip() if match else None
```

- [ ] **Step 9: Implementasi `app/services/ingestion/extractors/text.py`**

```python
"""Extractor untuk `.md`, `.markdown`, dan `.txt`."""

from pathlib import Path

from app.schemas.documents import ExtractedDocument
from app.services.ingestion.extractors.base import ProgressCallback
from app.services.ingestion.markdown_blocks import markdown_to_blocks


def extract_text(path: Path, *, on_progress: ProgressCallback | None = None) -> ExtractedDocument:
    """File teks dibaca apa adanya; heading markdown (kalau ada) jadi section."""
    blocks = markdown_to_blocks(path.read_text(encoding="utf-8", errors="replace"))
    if on_progress:
        on_progress(1.0)
    title = next((block.section for block in blocks if block.section), None)
    return ExtractedDocument(blocks=blocks, title=title)
```

- [ ] **Step 10: Implementasi `app/services/ingestion/extractors/__init__.py`**

```python
"""Registry extractor berdasarkan ekstensi file."""

from pathlib import Path

from app.services.ingestion.errors import UnsupportedFormatError
from app.services.ingestion.extractors.base import Extractor
from app.services.ingestion.extractors.html import extract_html
from app.services.ingestion.extractors.pdf import extract_pdf
from app.services.ingestion.extractors.text import extract_text

EXTRACTORS: dict[str, Extractor] = {
    ".pdf": extract_pdf,
    ".html": extract_html,
    ".htm": extract_html,
    ".md": extract_text,
    ".markdown": extract_text,
    ".txt": extract_text,
}

SUPPORTED_EXTENSIONS = frozenset(EXTRACTORS)


def get_extractor(path: Path) -> Extractor:
    """Pilih extractor dari ekstensi; pesan errornya menyebut apa yang tersedia."""
    suffix = path.suffix.lower()
    try:
        return EXTRACTORS[suffix]
    except KeyError:
        available = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFormatError(
            f"Format {suffix or '(tanpa ekstensi)'} belum didukung; yang tersedia: {available}"
        ) from None
```

- [ ] **Step 11: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_extractors.py -v
uv run ruff check .
```

Expected: 6 passed, ruff bersih.

Catatan: kalau `test_html_extraction_drops_boilerplate` gagal karena trafilatura
mengembalikan `None` (halaman contoh dianggap terlalu tipis), tambahkan satu paragraf
lagi ke `ARTICLE_HTML` — jangan melonggarkan assertion-nya.

- [ ] **Step 12: Commit**

```powershell
git add app/services/ingestion tests/pdf_factory.py tests/test_extractors.py
@'
feat: add pdf, html, and markdown extractors

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 6: Penyimpanan dokumen + streaming upload

**Files:**
- Create: `app/services/ingestion/store.py`, `app/services/ingestion/uploads.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Chunk`, `DocumentMeta` (Task 2); error domain (Task 5)
- Produces:
  - `DocumentStore(uploads_dir: Path, documents_dir: Path)` dengan `upload_path`, `exists`, `write_meta`, `read_meta`, `update_meta`, `list_meta`, `write_chunks`, `read_chunks`
  - `StoredUpload(doc_id, suffix, size_bytes, path)`
  - `stream_upload(upload, *, uploads_dir: Path, max_bytes: int) -> StoredUpload`

- [ ] **Step 1: Tulis test yang gagal — `tests/test_store.py`**

```python
"""Test penyimpanan dokumen di disk."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.schemas.documents import Chunk, DocumentMeta
from app.services.ingestion.errors import InvalidFileError, UploadTooLargeError
from app.services.ingestion.store import DocumentStore
from app.services.ingestion.uploads import stream_upload


class FakeUpload:
    """Cukup menyerupai `UploadFile` untuk test: punya `.filename` dan `.read()`."""

    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self, size: int) -> bytes:
        chunk, self._content = self._content[:size], self._content[size:]
        return chunk


def make_meta(doc_id: str = "abc123", *, status: str = "queued") -> DocumentMeta:
    now = datetime.now(UTC)
    return DocumentMeta(
        doc_id=doc_id,
        filename="dokumen.md",
        content_type="text/markdown",
        size_bytes=10,
        sha256=doc_id,
        status=status,
        stage="queued",
        created_at=now,
        updated_at=now,
    )


def make_chunk(index: int) -> Chunk:
    return Chunk(
        doc_id="abc123",
        chunk_index=index,
        text=f"chunk {index}",
        token_count=2,
        char_start=index * 10,
        char_end=index * 10 + 7,
    )


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    return DocumentStore(uploads_dir=tmp_path / "uploads", documents_dir=tmp_path / "documents")


def test_meta_round_trip(store: DocumentStore) -> None:
    meta = make_meta()

    store.write_meta(meta)

    assert store.read_meta(meta.doc_id) == meta
    assert store.exists(meta.doc_id)


def test_update_meta_changes_fields_and_timestamp(store: DocumentStore) -> None:
    meta = make_meta()
    store.write_meta(meta)

    updated = store.update_meta(meta.doc_id, status="completed", chunk_count=3)

    assert updated.status == "completed"
    assert updated.chunk_count == 3
    assert updated.updated_at > meta.updated_at
    assert store.read_meta(meta.doc_id).status == "completed"


def test_read_chunks_paginates(store: DocumentStore) -> None:
    store.write_chunks("abc123", [make_chunk(index) for index in range(5)])

    total, page = store.read_chunks("abc123", offset=2, limit=2)

    assert total == 5
    assert [chunk.chunk_index for chunk in page] == [2, 3]


def test_read_chunks_of_unknown_document_is_empty(store: DocumentStore) -> None:
    assert store.read_chunks("tidak-ada") == (0, [])


def test_list_meta_sorted_newest_first_and_skips_broken_file(store: DocumentStore) -> None:
    older = make_meta("older")
    older.created_at = datetime.now(UTC) - timedelta(days=1)
    older.updated_at = older.created_at
    newer = make_meta("newer")
    store.write_meta(older)
    store.write_meta(newer)
    broken = store.documents_dir / "rusak"
    broken.mkdir(parents=True)
    (broken / "meta.json").write_text("{ bukan json", encoding="utf-8")

    listed = store.list_meta()

    assert [meta.doc_id for meta in listed] == ["newer", "older"]


async def test_stream_upload_stores_content_addressed_file(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"

    stored = await stream_upload(
        FakeUpload("catatan.md", b"# Halo\n\nIsi."), uploads_dir=uploads, max_bytes=1000
    )

    assert stored.path == uploads / f"{stored.doc_id}.md"
    assert stored.size_bytes == 13
    assert stored.path.read_bytes() == b"# Halo\n\nIsi."


async def test_stream_upload_is_idempotent_for_same_content(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    content = b"# Sama\n"

    first = await stream_upload(FakeUpload("a.md", content), uploads_dir=uploads, max_bytes=1000)
    second = await stream_upload(FakeUpload("b.md", content), uploads_dir=uploads, max_bytes=1000)

    assert first.doc_id == second.doc_id
    assert len(list(uploads.glob("*.md"))) == 1


async def test_stream_upload_rejects_oversized_file(tmp_path: Path) -> None:
    with pytest.raises(UploadTooLargeError):
        await stream_upload(
            FakeUpload("besar.txt", b"x" * 50), uploads_dir=tmp_path / "uploads", max_bytes=10
        )

    assert list((tmp_path / "uploads").iterdir()) == []


async def test_stream_upload_rejects_pdf_without_magic_bytes(tmp_path: Path) -> None:
    with pytest.raises(InvalidFileError):
        await stream_upload(
            FakeUpload("palsu.pdf", b"bukan pdf sama sekali"),
            uploads_dir=tmp_path / "uploads",
            max_bytes=1000,
        )
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_store.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ingestion.store'`.

- [ ] **Step 3: Implementasi `app/services/ingestion/store.py`**

```python
"""Baca/tulis hasil ingestion di disk.

Tata letak:
    data/uploads/{doc_id}{ext}
    data/documents/{doc_id}/meta.json
    data/documents/{doc_id}/chunks.jsonl

Semua operasi berbasis path — tidak ada tipe HTTP di modul ini.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.documents import Chunk, DocumentMeta


class DocumentStore:
    """Akses file untuk dokumen: metadata dan chunk."""

    def __init__(self, *, uploads_dir: Path, documents_dir: Path) -> None:
        self.uploads_dir = uploads_dir
        self.documents_dir = documents_dir

    def upload_path(self, doc_id: str, suffix: str) -> Path:
        return self.uploads_dir / f"{doc_id}{suffix}"

    def exists(self, doc_id: str) -> bool:
        return self._meta_path(doc_id).exists()

    def write_meta(self, meta: DocumentMeta) -> None:
        path = self._meta_path(meta.doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(path, meta.model_dump_json(indent=2))

    def read_meta(self, doc_id: str) -> DocumentMeta:
        content = self._meta_path(doc_id).read_text(encoding="utf-8")
        return DocumentMeta.model_validate_json(content)

    def update_meta(self, doc_id: str, **fields: object) -> DocumentMeta:
        """Baca-ubah-tulis meta.json sekaligus memperbarui `updated_at`."""
        meta = self.read_meta(doc_id)
        updated = meta.model_copy(update={**fields, "updated_at": datetime.now(UTC)})
        self.write_meta(updated)
        return updated

    def list_meta(self) -> list[DocumentMeta]:
        """Semua dokumen, terbaru dulu; file rusak dilewati agar listing tetap hidup."""
        if not self.documents_dir.exists():
            return []
        metas: list[DocumentMeta] = []
        for meta_path in self.documents_dir.glob("*/meta.json"):
            try:
                metas.append(DocumentMeta.model_validate_json(meta_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(metas, key=lambda meta: meta.created_at, reverse=True)

    def write_chunks(self, doc_id: str, chunks: list[Chunk]) -> None:
        path = self.documents_dir / doc_id / "chunks.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")

    def read_chunks(
        self, doc_id: str, *, offset: int = 0, limit: int = 20
    ) -> tuple[int, list[Chunk]]:
        path = self.documents_dir / doc_id / "chunks.jsonl"
        if not path.exists():
            return 0, []
        chunks = [
            Chunk.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return len(chunks), chunks[offset : offset + limit]

    def _meta_path(self, doc_id: str) -> Path:
        return self.documents_dir / doc_id / "meta.json"

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        """Lewat file sementara: meta.json tidak pernah terbaca setengah jadi."""
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
```

- [ ] **Step 4: Implementasi `app/services/ingestion/uploads.py`**

```python
"""Terima upload HTTP dengan aman.

Nama file dari client **tidak pernah** dipakai sebagai path; file disimpan sebagai
`{sha256}{ekstensi}` sehingga path traversal tidak mungkin dan upload ulang dengan
isi sama otomatis idempotent.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.services.ingestion.errors import InvalidFileError, UploadTooLargeError

logger = logging.getLogger(__name__)

READ_SIZE = 1024 * 1024
PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class StoredUpload:
    """Hasil penyimpanan satu file upload."""

    doc_id: str
    suffix: str
    size_bytes: int
    path: Path


async def stream_upload(upload: UploadFile, *, uploads_dir: Path, max_bytes: int) -> StoredUpload:
    """Alirkan upload ke disk sambil menghitung sha256 dan menegakkan batas ukuran.

    File dibaca bertahap, jadi file raksasa tidak pernah masuk memori sekaligus.
    """
    uploads_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()
    incoming = uploads_dir / f".incoming-{uuid4().hex}"

    hasher = hashlib.sha256()
    size = 0
    try:
        with incoming.open("wb") as handle:
            while chunk := await upload.read(READ_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLargeError(
                        f"File melebihi batas {max_bytes // (1024 * 1024)} MB"
                    )
                hasher.update(chunk)
                handle.write(chunk)

        if suffix == ".pdf" and not _has_pdf_magic(incoming):
            raise InvalidFileError("File berekstensi .pdf tetapi isinya bukan PDF")

        doc_id = hasher.hexdigest()
        final = uploads_dir / f"{doc_id}{suffix}"
        if final.exists():
            incoming.unlink(missing_ok=True)
            logger.info("Isi file sudah pernah diunggah: %s", doc_id[:12])
        else:
            incoming.replace(final)
        return StoredUpload(doc_id=doc_id, suffix=suffix, size_bytes=size, path=final)
    except BaseException:
        incoming.unlink(missing_ok=True)
        raise


def _has_pdf_magic(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(PDF_MAGIC)) == PDF_MAGIC
```

- [ ] **Step 5: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_store.py -v
uv run ruff check .
```

Expected: 10 passed, ruff bersih.

- [ ] **Step 6: Commit**

```powershell
git add app/services/ingestion/store.py app/services/ingestion/uploads.py tests/test_store.py
@'
feat: add document store and safe upload streaming

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 7: Job runner + pipeline

**Files:**
- Create: `app/core/jobs.py`, `app/services/ingestion/pipeline.py`
- Test: `tests/test_jobs.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `DocumentStore` (Task 6), `get_extractor` (Task 5), `normalize_text` (Task 3), `chunk_document` (Task 4), `Settings` (Task 1)
- Produces:
  - `PROCESS_STARTED_AT: datetime`, `STALE_ERROR: str`
  - `JobState(doc_id, stage, progress)`
  - `JobRunner` dengan `submit(doc_id, coro)`, `state(doc_id)`, `is_running(doc_id)`, `stage(doc_id, stage, progress=None)`, `wait(doc_id)`, `shutdown()`
  - `ResolvedStatus(status, error)`, `resolve_status(meta, *, running) -> ResolvedStatus`
  - `StoreReporter(doc_id, runner, store)` dengan `stage(stage, progress=None)`
  - `ingest_file(*, doc_id, path, store, settings, reporter) -> None` (sinkron)
  - `run_ingestion(*, doc_id, path, store, settings, runner) -> None` (async)

- [ ] **Step 1: Tulis test yang gagal — `tests/test_jobs.py`**

```python
"""Test job runner dan penentuan status."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.jobs import PROCESS_STARTED_AT, STALE_ERROR, JobRunner, resolve_status
from tests.test_store import make_meta


async def test_wait_returns_after_job_finishes() -> None:
    runner = JobRunner()
    done = False

    async def job() -> None:
        nonlocal done
        await asyncio.sleep(0.01)
        done = True

    runner.submit("dokumen", job())
    await runner.wait("dokumen")

    assert done is True
    assert runner.is_running("dokumen") is False


def test_resolve_status_flags_orphan_job_as_failed() -> None:
    meta = make_meta(status="processing")
    meta.updated_at = PROCESS_STARTED_AT - timedelta(minutes=5)

    resolved = resolve_status(meta, running=False)

    assert resolved.status == "failed"
    assert resolved.error == STALE_ERROR


def test_resolve_status_keeps_running_job_processing() -> None:
    meta = make_meta(status="processing")
    meta.updated_at = PROCESS_STARTED_AT - timedelta(minutes=5)

    assert resolve_status(meta, running=True).status == "processing"


def test_resolve_status_leaves_completed_untouched() -> None:
    meta = make_meta(status="completed")
    meta.updated_at = datetime.now(UTC) - timedelta(days=3)

    assert resolve_status(meta, running=False).status == "completed"
```

- [ ] **Step 2: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_jobs.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.jobs'`.

- [ ] **Step 3: Implementasi `app/core/jobs.py`**

```python
"""Job ingestion in-process.

Kenapa in-process: belum ada masalah nyata yang menuntut queue eksternal. Yang hilang
saat restart hanyalah job yang sedang jalan — dan itu dideteksi `resolve_status` dengan
membandingkan `updated_at` terhadap waktu proses ini mulai, bukan dengan memindai disk
saat startup (pemindaian saat import akan menyentuh `data/` milik dev ketika test jalan).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.documents import DocumentMeta, DocumentStatus

logger = logging.getLogger(__name__)

PROCESS_STARTED_AT = datetime.now(UTC)
STALE_ERROR = "Server restart saat dokumen sedang diproses"


@dataclass
class JobState:
    """Progres satu job; hanya hidup selama proses ini berjalan."""

    doc_id: str
    stage: str | None = None
    progress: float | None = None


@dataclass(frozen=True)
class ResolvedStatus:
    """Status yang benar-benar dilaporkan ke pemanggil API."""

    status: DocumentStatus
    error: str | None


class JobRunner:
    """Menjalankan pekerjaan ingestion tanpa memblokir event loop.

    Yang berat (parsing) dijalankan di thread oleh pemanggil — lihat
    `app/services/ingestion/pipeline.py`.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._states: dict[str, JobState] = {}

    def submit(self, doc_id: str, coro) -> None:
        """Jadwalkan pekerjaan; referensi task disimpan supaya tidak di-GC."""
        self._states[doc_id] = JobState(doc_id=doc_id, stage="queued")
        task = asyncio.create_task(coro)
        self._tasks[doc_id] = task
        task.add_done_callback(lambda _task: self._forget(doc_id))
        logger.info("Job ingestion dijadwalkan untuk dokumen %s", doc_id[:12])

    def state(self, doc_id: str) -> JobState | None:
        return self._states.get(doc_id)

    def is_running(self, doc_id: str) -> bool:
        task = self._tasks.get(doc_id)
        return task is not None and not task.done()

    def stage(self, doc_id: str, stage: str, progress: float | None = None) -> None:
        self._states[doc_id] = JobState(doc_id=doc_id, stage=stage, progress=progress)

    async def wait(self, doc_id: str) -> None:
        """Tunggu satu job selesai — dipakai test dan shutdown.

        `shield` dipakai supaya pembatalan pada pihak yang menunggu tidak
        membatalkan pekerjaannya.
        """
        task = self._tasks.get(doc_id)
        if task is not None:
            await asyncio.shield(task)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                continue

    def _forget(self, doc_id: str) -> None:
        self._tasks.pop(doc_id, None)


def resolve_status(meta: DocumentMeta, *, running: bool) -> ResolvedStatus:
    """Hitung status yang dilaporkan: job yatim dari proses sebelumnya dianggap gagal."""
    if meta.status in ("queued", "processing") and not running and meta.updated_at < PROCESS_STARTED_AT:
        return ResolvedStatus(status="failed", error=STALE_ERROR)
    return ResolvedStatus(status=meta.status, error=meta.error)
```

- [ ] **Step 4: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_jobs.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Tulis test yang gagal — `tests/test_pipeline.py`**

```python
"""Test pipeline ingestion (sinkron, tanpa HTTP)."""

from pathlib import Path

from app.core.config import Settings
from app.core.jobs import JobRunner
from app.services.ingestion.pipeline import StoreReporter, ingest_file
from app.services.ingestion.store import DocumentStore
from tests.test_store import make_meta

DOCUMENT = """# Bab Satu

Paragraf pembuka yang menjelaskan isi dokumen dengan cukup panjang supaya
pemotongan benar-benar terjadi.

## Sub Bab

Paragraf kedua berisi detail tambahan tentang isi dokumen ini.
"""


def make_store(tmp_path: Path) -> DocumentStore:
    return DocumentStore(uploads_dir=tmp_path / "uploads", documents_dir=tmp_path / "documents")


def test_ingest_markdown_writes_meta_and_chunks(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "dokumen.md"
    path.write_text(DOCUMENT, encoding="utf-8")
    store.write_meta(make_meta("abc123"))
    reporter = StoreReporter(doc_id="abc123", runner=JobRunner(), store=store)

    ingest_file(
        doc_id="abc123",
        path=path,
        store=store,
        settings=Settings(_env_file=None, data_dir=tmp_path),
        reporter=reporter,
    )

    meta = store.read_meta("abc123")
    total, chunks = store.read_chunks("abc123")

    assert meta.status == "completed"
    assert meta.stage == "completed"
    assert meta.block_count == 2
    assert meta.chunk_count == total == len(chunks) == 2
    assert chunks[0].section == "Bab Satu"
    assert chunks[1].section == "Sub Bab"
    assert [chunk.doc_id for chunk in chunks] == ["abc123", "abc123"]


def test_reporter_does_not_rewrite_meta_for_repeated_stage(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write_meta(make_meta("abc123"))
    reporter = StoreReporter(doc_id="abc123", runner=JobRunner(), store=store)

    reporter.stage("extracting", 0.1)
    first = store.read_meta("abc123").updated_at
    reporter.stage("extracting", 0.5)

    assert store.read_meta("abc123").updated_at == first
```

Helper `make_meta` dipakai bersama oleh `tests/test_store.py`, `tests/test_jobs.py`, dan
`tests/test_pipeline.py`; definisinya ada di `tests/test_store.py`.

- [ ] **Step 6: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_pipeline.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ingestion.pipeline'`.

- [ ] **Step 7: Implementasi `app/services/ingestion/pipeline.py`**

```python
"""Orkestrasi ingestion: extract → normalize → chunk → simpan.

`ingest_file` sinkron dan dijalankan di thread oleh `run_ingestion`, karena
pdfplumber dan trafilatura sinkron dan CPU-bound: menjalankannya di event loop akan
menghentikan koneksi SSE yang sedang berjalan.
"""

import asyncio
import logging
from pathlib import Path

from app.core.chunking import chunk_document
from app.core.config import Settings
from app.core.jobs import JobRunner
from app.schemas.documents import Block
from app.services.ingestion.extractors import get_extractor
from app.services.ingestion.normalize import normalize_text
from app.services.ingestion.store import DocumentStore

logger = logging.getLogger(__name__)


class StoreReporter:
    """Pelapor kemajuan: stage disimpan ke registry (memori) dan ke meta.json.

    Progress per halaman hanya masuk memori; meta.json ditulis saat stage berganti
    supaya PDF ratusan halaman tidak menulis file ratusan kali.
    """

    def __init__(self, *, doc_id: str, runner: JobRunner, store: DocumentStore) -> None:
        self._doc_id = doc_id
        self._runner = runner
        self._store = store
        self._last_stage: str | None = None

    def stage(self, stage: str, progress: float | None = None) -> None:
        self._runner.stage(self._doc_id, stage, progress)
        if stage == self._last_stage:
            return
        self._store.update_meta(self._doc_id, stage=stage)
        self._last_stage = stage


def ingest_file(
    *,
    doc_id: str,
    path: Path,
    store: DocumentStore,
    settings: Settings,
    reporter: StoreReporter,
) -> None:
    """Seluruh pipeline untuk satu file (sinkron; dipanggil dari thread)."""
    reporter.stage("extracting", 0.0)
    extractor = get_extractor(path)
    extracted = extractor(path, on_progress=lambda value: reporter.stage("extracting", value))

    reporter.stage("normalizing")
    blocks: list[Block] = []
    for block in extracted.blocks:
        text = normalize_text(block.text)
        if text:
            blocks.append(
                Block(text=text, order=len(blocks), page=block.page, section=block.section)
            )

    reporter.stage("chunking")
    chunks = chunk_document(
        blocks,
        doc_id=doc_id,
        max_tokens=settings.chunk_max_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )

    reporter.stage("persisting")
    store.write_chunks(doc_id, chunks)
    store.update_meta(
        doc_id,
        status="completed",
        page_count=extracted.page_count,
        block_count=len(blocks),
        chunk_count=len(chunks),
        title=extracted.title,
        error=None,
    )
    reporter.stage("completed", 1.0)
    logger.info("Dokumen %s selesai: %d block → %d chunk", doc_id[:12], len(blocks), len(chunks))


async def run_ingestion(
    *,
    doc_id: str,
    path: Path,
    store: DocumentStore,
    settings: Settings,
    runner: JobRunner,
) -> None:
    """Bungkus `ingest_file` ke thread dan pastikan status selalu berakhir jelas."""
    store.update_meta(doc_id, status="processing", stage="extracting", error=None)
    reporter = StoreReporter(doc_id=doc_id, runner=runner, store=store)
    try:
        await asyncio.to_thread(
            ingest_file,
            doc_id=doc_id,
            path=path,
            store=store,
            settings=settings,
            reporter=reporter,
        )
    except Exception as exc:
        logger.exception("Ingestion gagal untuk dokumen %s", doc_id[:12])
        store.update_meta(doc_id, status="failed", stage="failed", error=str(exc))
```

- [ ] **Step 8: Jalankan test — harus LULUS**

```powershell
uv run pytest tests/test_pipeline.py tests/test_jobs.py -v
uv run ruff check .
```

Expected: 6 passed, ruff bersih.

- [ ] **Step 9: Commit**

```powershell
git add app/core/jobs.py app/services/ingestion/pipeline.py tests/test_jobs.py tests/test_pipeline.py
@'
feat: add job runner and ingestion pipeline

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 8: Endpoint API dokumen

**Files:**
- Create: `app/api/routes/documents.py`
- Modify: `app/api/deps.py`, `app/main.py`, `tests/conftest.py`
- Test: `tests/test_documents_api.py`

**Interfaces:**
- Consumes: semua task sebelumnya
- Produces: `documents.router` (`POST /api/documents`, `GET /api/documents`, `GET /api/documents/{id}`, `GET /api/documents/{id}/chunks`); `get_store`, `get_job_runner`; `app.state.job_runner`

- [ ] **Step 1: Sesuaikan fixture di `tests/conftest.py`**

Ganti isi berkas menjadi:

```python
"""Fixture bersama: app + AsyncClient + settings deterministik."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.core.jobs import JobRunner
from app.main import app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings test: tanpa baca .env, data di tmp_path, ping lama supaya tidak mengganggu."""
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        fake_token_delay_ms=1,
        sse_ping_interval_seconds=60,
    )


@pytest.fixture(autouse=True)
def fresh_job_runner() -> Iterator[None]:
    """Runner baru per test supaya status job tidak bocor antar-test."""
    previous = app.state.job_runner
    app.state.job_runner = JobRunner()
    yield
    app.state.job_runner = previous


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Client httpx yang bicara ke app lewat ASGI — tanpa server network."""
    app.dependency_overrides[get_settings] = lambda: settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Tambahkan dependency di `app/api/deps.py`**

Tambahkan import dan dua fungsi berikut (biarkan `get_streamer` apa adanya):

```python
from fastapi import Depends, Request

from app.core.jobs import JobRunner
from app.services.ingestion.store import DocumentStore


def get_store(settings: Annotated[Settings, Depends(get_settings)]) -> DocumentStore:
    """Store dibuat per request; isinya hanya path, jadi murah."""
    return DocumentStore(uploads_dir=settings.uploads_dir, documents_dir=settings.documents_dir)


def get_job_runner(request: Request) -> JobRunner:
    """Runner hidup di app.state supaya ikut siklus hidup aplikasi."""
    runner: JobRunner | None = getattr(request.app.state, "job_runner", None)
    if runner is None:
        raise RuntimeError("job_runner belum dipasang di app.state")
    return runner
```

- [ ] **Step 3: Pasang runner dan router di `app/main.py`**

```python
from app.api.routes import chat, documents, health
from app.core.jobs import JobRunner
```

lalu di dalam `create_app()`, sebelum `return app`:

```python
    app.state.job_runner = JobRunner()
    app.include_router(documents.router)
```

- [ ] **Step 4: Tulis test yang gagal — `tests/test_documents_api.py`**

```python
"""Test endpoint ingestion dokumen."""

import httpx

from app.core.config import Settings, get_settings
from app.main import app
from tests.pdf_factory import build_pdf

MARKDOWN = "# Bab Satu\n\nIsi dokumen uji yang cukup panjang untuk dipotong menjadi beberapa bagian.\n"


async def upload(client: httpx.AsyncClient, *, filename: str, content: bytes, content_type: str = "text/plain"):
    return await client.post(
        "/api/documents", files={"file": (filename, content, content_type)}
    )


async def wait_for_job(document_id: str) -> None:
    await app.state.job_runner.wait(document_id)


async def test_markdown_upload_is_processed_and_listed(client: httpx.AsyncClient) -> None:
    response = await upload(client, filename="catatan.md", content=MARKDOWN.encode())
    assert response.status_code == 202
    document_id = response.json()["document_id"]
    assert response.headers["location"] == f"/api/documents/{document_id}"

    await wait_for_job(document_id)

    status = (await client.get(f"/api/documents/{document_id}")).json()
    assert status["status"] == "completed"
    assert status["chunk_count"] >= 1
    assert status["stage"] == "completed"

    chunks = (await client.get(f"/api/documents/{document_id}/chunks")).json()
    assert chunks["total"] == status["chunk_count"]
    assert chunks["chunks"][0]["section"] == "Bab Satu"

    listed = (await client.get("/api/documents")).json()
    assert [document["document_id"] for document in listed["documents"]] == [document_id]


async def test_pdf_upload_records_page_count(client: httpx.AsyncClient) -> None:
    content = build_pdf(["Halaman satu.", "Halaman dua."])

    response = await upload(client, filename="dua.pdf", content=content, content_type="application/pdf")
    assert response.status_code == 202

    document_id = response.json()["document_id"]
    await wait_for_job(document_id)

    status = (await client.get(f"/api/documents/{document_id}")).json()
    assert status["status"] == "completed"
    assert status["page_count"] == 2


async def test_uploading_same_content_twice_is_idempotent(client: httpx.AsyncClient) -> None:
    first = await upload(client, filename="sama.md", content=MARKDOWN.encode())
    document_id = first.json()["document_id"]
    await wait_for_job(document_id)

    second = await upload(client, filename="sama-lagi.md", content=MARKDOWN.encode())

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["document_id"] == document_id


async def test_failed_document_can_be_retried(client: httpx.AsyncClient) -> None:
    broken = build_pdf([""])  # tidak punya lapisan teks → gagal
    first = await upload(client, filename="scan.pdf", content=broken, content_type="application/pdf")
    document_id = first.json()["document_id"]
    await wait_for_job(document_id)

    failed = (await client.get(f"/api/documents/{document_id}")).json()
    assert failed["status"] == "failed"
    assert "OCR" in failed["error"]

    retry = await upload(client, filename="scan.pdf", content=broken, content_type="application/pdf")

    assert retry.status_code == 202
    assert retry.json()["duplicate"] is False


async def test_unsupported_extension_is_rejected(client: httpx.AsyncClient) -> None:
    response = await upload(client, filename="data.xlsx", content=b"apapun")

    assert response.status_code == 415


async def test_fake_pdf_is_rejected(client: httpx.AsyncClient) -> None:
    response = await upload(client, filename="palsu.pdf", content=b"ini teks biasa")

    assert response.status_code == 415


async def test_oversized_file_is_rejected(client: httpx.AsyncClient, settings: Settings) -> None:
    tiny_limit = settings.model_copy(update={"max_upload_bytes": 8})
    app.dependency_overrides[get_settings] = lambda: tiny_limit
    try:
        response = await upload(client, filename="besar.md", content=b"x" * 100)
    finally:
        app.dependency_overrides[get_settings] = lambda: settings

    assert response.status_code == 413


async def test_unknown_document_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/documents/tidak-ada")

    assert response.status_code == 404
```

- [ ] **Step 5: Jalankan test — harus GAGAL**

```powershell
uv run pytest tests/test_documents_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.routes.documents'`.

- [ ] **Step 6: Implementasi `app/api/routes/documents.py`**

```python
"""Endpoint ingestion dokumen."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import get_job_runner, get_store
from app.core.config import Settings, get_settings
from app.core.jobs import JobRunner, resolve_status
from app.schemas.documents import (
    ChunkListResponse,
    DocumentListResponse,
    DocumentMeta,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.ingestion.errors import InvalidFileError, UploadTooLargeError
from app.services.ingestion.extractors import SUPPORTED_EXTENSIONS
from app.services.ingestion.pipeline import run_ingestion
from app.services.ingestion.store import DocumentStore
from app.services.ingestion.uploads import stream_upload

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    response: Response,
    store: Annotated[DocumentStore, Depends(get_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentUploadResponse:
    """Simpan file lalu proses di background; respons tidak menunggu selesai."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        available = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Format {suffix or '(tanpa ekstensi)'} tidak didukung; gunakan {available}",
        )

    try:
        stored = await stream_upload(
            file, uploads_dir=settings.uploads_dir, max_bytes=settings.max_upload_bytes
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except InvalidFileError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    existing = store.read_meta(stored.doc_id) if store.exists(stored.doc_id) else None
    if existing is not None:
        resolved = resolve_status(existing, running=runner.is_running(stored.doc_id))
        if resolved.status != "failed":
            response.status_code = status.HTTP_200_OK
            return DocumentUploadResponse(
                document_id=existing.doc_id,
                filename=existing.filename,
                size_bytes=existing.size_bytes,
                status=resolved.status,
                duplicate=True,
            )

    now = datetime.now(UTC)
    meta = DocumentMeta(
        doc_id=stored.doc_id,
        filename=file.filename or stored.path.name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        sha256=stored.doc_id,
        status="queued",
        stage="queued",
        created_at=now,
        updated_at=now,
    )
    store.write_meta(meta)
    runner.submit(
        stored.doc_id,
        run_ingestion(
            doc_id=stored.doc_id,
            path=stored.path,
            store=store,
            settings=settings,
            runner=runner,
        ),
    )

    response.headers["Location"] = f"/api/documents/{stored.doc_id}"
    return DocumentUploadResponse(
        document_id=stored.doc_id,
        filename=meta.filename,
        size_bytes=meta.size_bytes,
        status="queued",
        duplicate=False,
    )


@router.get("")
async def list_documents(
    store: Annotated[DocumentStore, Depends(get_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
) -> DocumentListResponse:
    """Semua dokumen yang pernah diunggah, terbaru dulu."""
    documents = [
        _status_response(meta, runner=runner) for meta in store.list_meta()
    ]
    return DocumentListResponse(documents=documents)


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
) -> DocumentStatusResponse:
    """Status satu dokumen, termasuk progres job yang sedang berjalan."""
    meta = _read_meta_or_404(store, document_id)
    return _status_response(meta, runner=runner)


@router.get("/{document_id}/chunks")
async def list_chunks(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ChunkListResponse:
    """Isi chunk — untuk pemeriksaan manual dan (nanti) menampilkan sumber di UI."""
    _read_meta_or_404(store, document_id)
    total, chunks = store.read_chunks(document_id, offset=offset, limit=limit)
    return ChunkListResponse(
        document_id=document_id, total=total, offset=offset, limit=limit, chunks=chunks
    )


def _read_meta_or_404(store: DocumentStore, document_id: str) -> DocumentMeta:
    if not store.exists(document_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokumen tidak ditemukan")
    return store.read_meta(document_id)


def _status_response(meta: DocumentMeta, *, runner: JobRunner) -> DocumentStatusResponse:
    """Gabungkan meta.json dengan state job di memori (kalau ada)."""
    resolved = resolve_status(meta, running=runner.is_running(meta.doc_id))
    job = runner.state(meta.doc_id)
    data = meta.model_dump()
    data.update(
        status=resolved.status,
        error=resolved.error,
        progress=job.progress if job and resolved.status == meta.status else None,
    )
    return DocumentStatusResponse(**data)
```

- [ ] **Step 7: Jalankan test — harus LULUS**

```powershell
uv run pytest -v
uv run ruff check .
```

Expected: seluruh test task 1 + task 2 lulus, ruff bersih.

- [ ] **Step 8: Commit**

```powershell
git add app/api app/main.py tests/conftest.py tests/test_documents_api.py
@'
feat: add document upload and status endpoints

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```

---

## Task 9: Verifikasi manual + dokumentasi

**Files:**
- Create: `docs/learning/ingestion-chunking.md`
- Modify: `README.md`, `docs/README.md`, `docs/decisions.md` (kalau ada yang bergeser), `.env.example` (kalau ada setelan baru)

**Interfaces:**
- Consumes: seluruh hasil Task 1–8
- Produces: angka nyata (ukuran chunk, waktu proses, perilaku event loop) yang jadi rujukan task 3–4

- [ ] **Step 1: Jalankan server dan unggah dokumen nyata**

```powershell
uv run uvicorn app.main:app --port 8000
```

Di terminal kedua (ganti nama file sesuai dokumen yang ada):

```powershell
$pdf = "docs/learning/fastapi-async-sse.md"   # ganti dengan PDF/HTML nyata milikmu
curl.exe -sS -X POST http://127.0.0.1:8000/api/documents -F "file=@$pdf;filename=dokumen.md"
```

Expected: JSON dengan `document_id` dan `status: "queued"`.

- [ ] **Step 2: Periksa hasil di disk**

```powershell
Get-ChildItem data/documents/*/ | Select-Object FullName
Get-Content (Get-ChildItem data/documents/*/meta.json | Select-Object -First 1) -Raw
```

Catat: `chunk_count`, `block_count`, `page_count`, dan isi satu chunk untuk menilai
kualitas pemotongan.

- [ ] **Step 3: Ukur sebaran ukuran chunk**

```powershell
@'
import json
import statistics
from pathlib import Path

files = sorted(Path("data/documents").glob("*/chunks.jsonl"))
for path in files:
    chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    sizes = [chunk["token_count"] for chunk in chunks]
    print(f"{path.parent.name[:12]}  chunks={len(chunks)}  min={min(sizes)} max={max(sizes)} rata2={statistics.mean(sizes):.0f}")
'@ | uv run python -
```

Expected: ukuran maksimum ≤ 800; sebagian besar mendekati 700-an kalau dokumennya panjang.
Chunk terakhir biasanya jauh lebih pendek (sisa pembagian) — itu perilaku yang memang
diterima di task ini. Kalau ada chunk pendek di **tengah** dokumen, itu tanda batas
section atau paragraf memotong lebih awal; catat temuannya, jangan langsung ubah angkanya.

- [ ] **Step 4: Eksperimen event loop (inti dari desain `to_thread`)**

Dengan server berjalan, streaming chat di satu terminal:

```powershell
'{"message": "jeda"}' | curl.exe -N -sS -X POST "http://127.0.0.1:8000/api/chat/stream" -H "Content-Type: application/json" -d "@-"
```

Sementara itu, di terminal lain, unggah PDF besar (belasan halaman). Amati apakah frame
`: ping` tetap muncul tepat waktu selama ingestion berjalan.

Untuk pembanding, ubah sementara di `packages` route: panggil `ingest_file` langsung
(sinkron) tanpa `asyncio.to_thread`, jalankan ulang eksperimen, catat jitter yang muncul,
lalu **kembalikan perubahan itu**. Catat kedua hasilnya di dokumen learning.

- [ ] **Step 5: Tulis `docs/learning/ingestion-chunking.md`**

Heading wajib, berurutan:

1. `## Konsep` — chunking, mengapa token bukan karakter, recursive split, overlap.
2. `## Alur data di repo ini` — diagram ASCII upload → extractor → blocks → chunker → disk.
3. `## Keputusan & kenapa` — pdfplumber vs alternatif, trafilatura, blocks vs string panjang, in-process job, `to_thread`.
4. `## Hasil percobaan` — tempel output Step 2–4 apa adanya, termasuk yang mengejutkan.
5. `## Failure mode` — tabel: scan PDF, PDF rusak, HTML tanpa isi, restart saat proses, disk penuh, parser menggantung (utang task 9).
6. `## Catatan produksi` — biaya, waktu proses per halaman, batas ukuran, kenapa job hilang saat restart.
7. `## Cara menjalankan & menguji`.
8. `## Poin Kunci` — 3–5 bullet.
9. `## Eksperimen lanjutan` — 2 ide (mis. bandingkan dengan `RecursiveCharacterTextSplitter` LangChain; coba chunking semantik).
10. `## Glosarium` — istilah + kepanjangan (termasuk OCR, boilerplate, JSONL, sha256, thread pool, event loop).

- [ ] **Step 6: Perbarui `README.md` dan `docs/README.md`**

- `README.md`: tambahkan 3 endpoint dokumen + contoh `curl -F` upload + catatan bahwa `data/` menyimpan hasil.
- `docs/README.md`: status spec/plan task 2 + link dokumen learning baru.

- [ ] **Step 7: Verifikasi akhir**

```powershell
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
git status --short
```

Expected: semua test lulus, ruff bersih, tidak ada file tak terduga (terutama tidak ada
`data/` yang ikut ter-stage).

- [ ] **Step 8: Commit**

```powershell
git add README.md docs
@'
docs: add task 2 learning notes and refresh project docs

Co-authored-by: CommandCodeBot <noreply@commandcode.ai>
'@ | git commit -F -
```
