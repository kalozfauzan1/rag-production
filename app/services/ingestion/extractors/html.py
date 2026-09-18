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
