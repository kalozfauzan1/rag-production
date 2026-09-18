"""Test perilaku level aplikasi (middleware, halaman statis)."""

import httpx


async def test_cors_headers_for_frontend_origin(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
