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
    assert stored.size_bytes == 12
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
