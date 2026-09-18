"""Error domain ingestion — dipetakan ke kode HTTP di lapisan API."""


class IngestionError(Exception):
    """Induk semua error ingestion."""


class UnsupportedFormatError(IngestionError):
    """Ekstensi file tidak punya extractor."""


class InvalidFileError(IngestionError):
    """Isi file tidak cocok dengan tipenya (mis. `.pdf` tanpa header `%PDF-`)."""


class UploadTooLargeError(IngestionError):
    """File melebihi batas `MAX_UPLOAD_BYTES`."""


class ExtractionError(IngestionError):
    """Gagal mengekstrak isi file (rusak, terenkripsi, dan sejenisnya)."""


class ScannedPdfError(ExtractionError):
    """PDF tidak punya lapisan teks — kemungkinan hasil scan; OCR belum didukung."""
