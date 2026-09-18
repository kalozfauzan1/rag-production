"""Titik masuk ASGI: app factory, CORS, dan router."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import chat, documents, health
from app.core.config import get_settings
from app.core.jobs import JobRunner

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    # Uvicorn hanya mengatur logger `uvicorn.*`; tanpa ini log aplikasi
    # (mis. catatan client disconnect) tidak akan terlihat sama sekali.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    app = FastAPI(title="rag-production API", version="0.1.0")

    # Frontend Next.js (task 7) jalan di origin berbeda saat dev,
    # jadi browser butuh izin CORS eksplisit.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(documents.router)

    # Runner job ikut siklus hidup aplikasi; task yang sedang jalan akan dibatalkan
    # saat shutdown, dan `resolve_status` yang menandainya gagal pada proses berikutnya.
    app.state.job_runner = JobRunner()

    @app.get("/demo", include_in_schema=False)
    async def demo() -> FileResponse:
        """Halaman uji manual untuk melihat frame SSE apa adanya."""
        return FileResponse(STATIC_DIR / "stream-demo.html")

    return app


app = create_app()
