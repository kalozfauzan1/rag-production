"""Titik masuk ASGI: app factory, CORS, dan router."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health
from app.core.config import get_settings


def create_app() -> FastAPI:
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

    return app


app = create_app()
