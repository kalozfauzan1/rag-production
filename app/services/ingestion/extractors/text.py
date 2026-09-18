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
