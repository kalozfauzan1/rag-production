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
