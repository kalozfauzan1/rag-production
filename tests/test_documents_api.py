"""Test endpoint ingestion dokumen."""

import httpx

from app.core.config import Settings, get_settings
from app.main import app
from tests.pdf_factory import build_pdf

MARKDOWN = (
    "# Bab Satu\n\nIsi dokumen uji yang cukup panjang untuk dipotong menjadi beberapa bagian.\n"
)


async def upload(
    client: httpx.AsyncClient,
    *,
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
) -> httpx.Response:
    return await client.post("/api/documents", files={"file": (filename, content, content_type)})


async def wait_for_job(document_id: str) -> None:
    await app.state.job_runner.wait(document_id)


async def test_markdown_upload_is_processed_and_listed(client: httpx.AsyncClient) -> None:
    response = await upload(client, filename="catatan.md", content=MARKDOWN.encode())
    assert response.status_code == 202
    document_id = response.json()["document_id"]
    assert response.headers["location"] == f"/api/documents/{document_id}"

    await wait_for_job(document_id)

    status = (await client.get(f"/api/documents/{document_id}")).json()
    assert status["status"] == "completed", status.get("error")
    assert status["chunk_count"] >= 1
    assert status["stage"] == "completed"

    chunks = (await client.get(f"/api/documents/{document_id}/chunks")).json()
    assert chunks["total"] == status["chunk_count"]
    assert chunks["chunks"][0]["section"] == "Bab Satu"

    listed = (await client.get("/api/documents")).json()
    assert [document["document_id"] for document in listed["documents"]] == [document_id]


async def test_pdf_upload_records_page_count(client: httpx.AsyncClient) -> None:
    content = build_pdf(
        [
            "Halaman pertama berisi teks yang cukup panjang untuk melewati ambang deteksi scan.",
            "Halaman kedua juga berisi teks yang panjangnya memadai untuk pengujian.",
        ]
    )

    response = await upload(
        client, filename="dua.pdf", content=content, content_type="application/pdf"
    )
    assert response.status_code == 202

    document_id = response.json()["document_id"]
    await wait_for_job(document_id)

    status = (await client.get(f"/api/documents/{document_id}")).json()
    assert status["status"] == "completed", status.get("error")
    assert status["page_count"] == 2


async def test_uploading_same_content_twice_is_idempotent(client: httpx.AsyncClient) -> None:
    first = await upload(client, filename="sama.md", content=MARKDOWN.encode())
    document_id = first.json()["document_id"]
    await wait_for_job(document_id)

    second = await upload(client, filename="sama-lagi.md", content=MARKDOWN.encode())

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["document_id"] == document_id


async def test_failed_document_can_be_retried(client: httpx.AsyncClient) -> None:
    broken = build_pdf([""])  # tidak punya lapisan teks → gagal
    first = await upload(
        client, filename="scan.pdf", content=broken, content_type="application/pdf"
    )
    document_id = first.json()["document_id"]
    await wait_for_job(document_id)

    failed = (await client.get(f"/api/documents/{document_id}")).json()
    assert failed["status"] == "failed"
    assert "OCR" in failed["error"]

    retry = await upload(
        client, filename="scan.pdf", content=broken, content_type="application/pdf"
    )

    assert retry.status_code == 202
    assert retry.json()["duplicate"] is False


async def test_unsupported_extension_is_rejected(client: httpx.AsyncClient) -> None:
    response = await upload(client, filename="data.xlsx", content=b"apapun")

    assert response.status_code == 415


async def test_fake_pdf_is_rejected(client: httpx.AsyncClient) -> None:
    response = await upload(client, filename="palsu.pdf", content=b"ini teks biasa")

    assert response.status_code == 415


async def test_oversized_file_is_rejected(client: httpx.AsyncClient, settings: Settings) -> None:
    tiny_limit = settings.model_copy(update={"max_upload_bytes": 8})
    app.dependency_overrides[get_settings] = lambda: tiny_limit
    try:
        response = await upload(client, filename="besar.md", content=b"x" * 100)
    finally:
        app.dependency_overrides[get_settings] = lambda: settings

    assert response.status_code == 413


async def test_unknown_document_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/documents/tidak-ada")

    assert response.status_code == 404
