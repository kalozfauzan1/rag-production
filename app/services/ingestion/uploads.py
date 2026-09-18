"""Terima upload HTTP dengan aman.

Nama file dari client **tidak pernah** dipakai sebagai path; file disimpan sebagai
`{sha256}{ekstensi}` sehingga path traversal tidak mungkin dan upload ulang dengan
isi sama otomatis idempotent.

Operasi disk dijalankan lewat `asyncio.to_thread`: menulis file langsung di dalam event
loop akan menghentikan koneksi SSE yang sedang berjalan — pelajaran yang sama seperti
parsing PDF di pipeline.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.services.ingestion.errors import InvalidFileError, UploadTooLargeError

logger = logging.getLogger(__name__)

READ_SIZE = 1024 * 1024
PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class StoredUpload:
    """Hasil penyimpanan satu file upload."""

    doc_id: str
    suffix: str
    size_bytes: int
    path: Path


async def stream_upload(upload: UploadFile, *, uploads_dir: Path, max_bytes: int) -> StoredUpload:
    """Alirkan upload ke disk sambil menghitung sha256 dan menegakkan batas ukuran.

    File dibaca bertahap, jadi file raksasa tidak pernah masuk memori sekaligus.
    """
    await asyncio.to_thread(uploads_dir.mkdir, parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()
    incoming = uploads_dir / f".incoming-{uuid4().hex}"

    hasher = hashlib.sha256()
    size = 0
    try:
        handle = await asyncio.to_thread(incoming.open, "wb")
        try:
            while chunk := await upload.read(READ_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    limit_mb = max_bytes // (1024 * 1024)
                    raise UploadTooLargeError(f"File melebihi batas {limit_mb} MB")
                hasher.update(chunk)
                await asyncio.to_thread(handle.write, chunk)
        finally:
            await asyncio.to_thread(handle.close)

        if suffix == ".pdf" and not await asyncio.to_thread(_has_pdf_magic, incoming):
            raise InvalidFileError("File berekstensi .pdf tetapi isinya bukan PDF")

        doc_id = hasher.hexdigest()
        final = uploads_dir / f"{doc_id}{suffix}"
        if await asyncio.to_thread(final.exists):
            await asyncio.to_thread(incoming.unlink, missing_ok=True)
            logger.info("Isi file sudah pernah diunggah: %s", doc_id[:12])
        else:
            await asyncio.to_thread(incoming.replace, final)
        return StoredUpload(doc_id=doc_id, suffix=suffix, size_bytes=size, path=final)
    except BaseException:
        # Jalur error (termasuk pembatalan): sengaja sinkron dan tanpa await, supaya
        # file sementara tetap terhapus walau task sedang dibatalkan.
        incoming.unlink(missing_ok=True)  # noqa: ASYNC240
        raise


def _has_pdf_magic(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(PDF_MAGIC)) == PDF_MAGIC
