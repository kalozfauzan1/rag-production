"""Orkestrasi ingestion: extract → normalize → chunk → simpan.

`ingest_file` sinkron dan dijalankan di thread oleh `run_ingestion`, karena pdfplumber
dan trafilatura sinkron dan CPU-bound: menjalankannya di event loop akan menghentikan
koneksi SSE yang sedang berjalan.
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
    """Pelapor kemajuan: stage masuk ke registry (memori) dan ke meta.json.

    Progress per halaman hanya disimpan di memori; meta.json ditulis saat stage
    berganti, supaya PDF ratusan halaman tidak menulis file ratusan kali.
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
    logger.info("Dokumen %s selesai: %d block -> %d chunk", doc_id[:12], len(blocks), len(chunks))


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
