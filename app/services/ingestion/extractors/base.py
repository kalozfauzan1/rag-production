"""Kontrak extractor: file → ExtractedDocument.

Semua extractor **sinkron** dan dipanggil dari thread oleh pipeline, karena pdfplumber
dan trafilatura sinkron dan CPU-bound.
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
