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
