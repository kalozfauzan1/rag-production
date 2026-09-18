"""Endpoint pengecekan kesehatan service."""

from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Dipakai uptime check / load balancer (Railway, Fly)."""
    return {"status": "ok"}
