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
