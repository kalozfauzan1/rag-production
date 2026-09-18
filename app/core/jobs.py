"""Job ingestion in-process.

Kenapa in-process: belum ada masalah nyata yang menuntut queue eksternal. Yang hilang
saat restart hanyalah job yang sedang jalan — dan itu dideteksi `resolve_status` dengan
membandingkan `updated_at` terhadap waktu proses ini mulai, bukan dengan memindai disk
saat startup (pemindaian saat import akan menyentuh `data/` milik dev ketika test jalan).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.schemas.documents import DocumentMeta, DocumentStatus

logger = logging.getLogger(__name__)

PROCESS_STARTED_AT = datetime.now(UTC)
STALE_ERROR = "Server restart saat dokumen sedang diproses"


@dataclass
class JobState:
    """Progres satu job; hanya hidup selama proses ini berjalan."""

    doc_id: str
    stage: str | None = None
    progress: float | None = None


@dataclass(frozen=True)
class ResolvedStatus:
    """Status yang benar-benar dilaporkan ke pemanggil API."""

    status: DocumentStatus
    error: str | None


class JobRunner:
    """Menjalankan pekerjaan ingestion tanpa memblokir event loop.

    Yang berat (parsing, tulis file) dijalankan di thread oleh pemanggil — lihat
    `app/services/ingestion/pipeline.py`.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._states: dict[str, JobState] = {}

    def submit(self, doc_id: str, coro: Any) -> None:
        """Jadwalkan pekerjaan; referensi task disimpan supaya tidak di-GC."""
        self._states[doc_id] = JobState(doc_id=doc_id, stage="queued")
        task = asyncio.create_task(coro)
        self._tasks[doc_id] = task
        task.add_done_callback(lambda _task: self._forget(doc_id))
        logger.info("Job ingestion dijadwalkan untuk dokumen %s", doc_id[:12])

    def state(self, doc_id: str) -> JobState | None:
        return self._states.get(doc_id)

    def is_running(self, doc_id: str) -> bool:
        task = self._tasks.get(doc_id)
        return task is not None and not task.done()

    def stage(self, doc_id: str, stage: str, progress: float | None = None) -> None:
        self._states[doc_id] = JobState(doc_id=doc_id, stage=stage, progress=progress)

    async def wait(self, doc_id: str) -> None:
        """Tunggu satu job selesai — dipakai test dan shutdown.

        `shield` dipakai supaya pembatalan pada pihak yang menunggu tidak ikut
        membatalkan pekerjaannya.
        """
        task = self._tasks.get(doc_id)
        if task is not None:
            await asyncio.shield(task)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                continue

    def _forget(self, doc_id: str) -> None:
        self._tasks.pop(doc_id, None)


def resolve_status(meta: DocumentMeta, *, running: bool) -> ResolvedStatus:
    """Hitung status yang dilaporkan: job yatim dari proses sebelumnya dianggap gagal."""
    orphaned = (
        meta.status in ("queued", "processing")
        and not running
        and meta.updated_at < PROCESS_STARTED_AT
    )
    if orphaned:
        return ResolvedStatus(status="failed", error=STALE_ERROR)
    return ResolvedStatus(status=meta.status, error=meta.error)
