"""Endpoint ingestion dokumen."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import get_job_runner, get_store
from app.core.config import Settings, get_settings
from app.core.jobs import JobRunner, resolve_status
from app.schemas.documents import (
    ChunkListResponse,
    DocumentListResponse,
    DocumentMeta,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.ingestion.errors import InvalidFileError, UploadTooLargeError
from app.services.ingestion.extractors import SUPPORTED_EXTENSIONS
from app.services.ingestion.pipeline import run_ingestion
from app.services.ingestion.store import DocumentStore
from app.services.ingestion.uploads import stream_upload

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    response: Response,
    store: Annotated[DocumentStore, Depends(get_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentUploadResponse:
    """Simpan file lalu proses di background; respons tidak menunggu selesai."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        available = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Format {suffix or '(tanpa ekstensi)'} tidak didukung; gunakan {available}",
        )

    try:
        stored = await stream_upload(
            file, uploads_dir=settings.uploads_dir, max_bytes=settings.max_upload_bytes
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except InvalidFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc

    existing = store.read_meta(stored.doc_id) if store.exists(stored.doc_id) else None
    if existing is not None:
        resolved = resolve_status(existing, running=runner.is_running(stored.doc_id))
        if resolved.status != "failed":
            response.status_code = status.HTTP_200_OK
            return DocumentUploadResponse(
                document_id=existing.doc_id,
                filename=existing.filename,
                size_bytes=existing.size_bytes,
                status=resolved.status,
                duplicate=True,
            )

    now = datetime.now(UTC)
    meta = DocumentMeta(
        doc_id=stored.doc_id,
        filename=file.filename or stored.path.name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        sha256=stored.doc_id,
        status="queued",
        stage="queued",
        created_at=now,
        updated_at=now,
    )
    store.write_meta(meta)
    runner.submit(
        stored.doc_id,
        run_ingestion(
            doc_id=stored.doc_id,
            path=stored.path,
            store=store,
            settings=settings,
            runner=runner,
        ),
    )

    response.headers["Location"] = f"/api/documents/{stored.doc_id}"
    return DocumentUploadResponse(
        document_id=stored.doc_id,
        filename=meta.filename,
        size_bytes=meta.size_bytes,
        status="queued",
        duplicate=False,
    )


@router.get("")
async def list_documents(
    store: Annotated[DocumentStore, Depends(get_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
) -> DocumentListResponse:
    """Semua dokumen yang pernah diunggah, terbaru dulu."""
    documents = [_status_response(meta, runner=runner) for meta in store.list_meta()]
    return DocumentListResponse(documents=documents)


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
) -> DocumentStatusResponse:
    """Status satu dokumen, termasuk progres job yang sedang berjalan."""
    meta = _read_meta_or_404(store, document_id)
    return _status_response(meta, runner=runner)


@router.get("/{document_id}/chunks")
async def list_chunks(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ChunkListResponse:
    """Isi chunk — untuk pemeriksaan manual dan (nanti) menampilkan sumber di UI."""
    _read_meta_or_404(store, document_id)
    total, chunks = store.read_chunks(document_id, offset=offset, limit=limit)
    return ChunkListResponse(
        document_id=document_id, total=total, offset=offset, limit=limit, chunks=chunks
    )


def _read_meta_or_404(store: DocumentStore, document_id: str) -> DocumentMeta:
    if not store.exists(document_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokumen tidak ditemukan")
    return store.read_meta(document_id)


def _status_response(meta: DocumentMeta, *, runner: JobRunner) -> DocumentStatusResponse:
    """Gabungkan meta.json dengan state job di memori (kalau ada)."""
    resolved = resolve_status(meta, running=runner.is_running(meta.doc_id))
    job = runner.state(meta.doc_id)
    return DocumentStatusResponse(
        document_id=meta.doc_id,
        filename=meta.filename,
        content_type=meta.content_type,
        size_bytes=meta.size_bytes,
        sha256=meta.sha256,
        status=resolved.status,
        stage=meta.stage,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        page_count=meta.page_count,
        block_count=meta.block_count,
        chunk_count=meta.chunk_count,
        title=meta.title,
        error=resolved.error,
        progress=job.progress if job and resolved.status == meta.status else None,
    )
