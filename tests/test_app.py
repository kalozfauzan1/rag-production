"""Test perilaku level aplikasi (middleware, halaman statis)."""

import httpx


async def test_cors_headers_for_frontend_origin(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_demo_page_is_served(client: httpx.AsyncClient) -> None:
    response = await client.get("/demo")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
