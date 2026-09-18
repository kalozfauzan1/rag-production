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
