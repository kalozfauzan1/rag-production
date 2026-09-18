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
    ternormalisasi (tidak termasuk teks overlap yang disalin dari chunk sebelumnya).
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


class DocumentStatusResponse(BaseModel):
    """Bentuk satu dokumen di API: isi `meta.json` + progres job yang berjalan.

    Sengaja tidak mewarisi `DocumentMeta`: kontrak API memakai `document_id`,
    sedangkan penyimpanan memakai `doc_id`. Pemisahan ini menjaga format file di disk
    tidak ikut berubah kalau penamaan di API berubah.
    """

    document_id: str
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
    progress: float | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentStatusResponse]


class ChunkListResponse(BaseModel):
    document_id: str
    total: int
    offset: int
    limit: int
    chunks: list[Chunk]
