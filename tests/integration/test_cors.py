from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.cors import install_cors_middleware
from app.api.errors import install_error_handlers, install_request_id_middleware


@pytest.mark.asyncio
async def test_configured_browser_origin_can_preflight_authenticated_api() -> None:
    app = FastAPI()
    install_cors_middleware(app, ("https://ogaforeman.example",))

    @app.get("/api/v1/projects")
    async def projects() -> dict[str, list[object]]:
        return {"data": []}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.options(
            "/api/v1/projects",
            headers={
                "Origin": "https://ogaforeman.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,x-request-id",
            },
        )
        denied = await client.options(
            "/api/v1/projects",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://ogaforeman.example"
    assert "authorization" in allowed.headers["access-control-allow-headers"].lower()
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.asyncio
async def test_configured_browser_origin_receives_cors_headers_on_server_error() -> None:
    app = FastAPI()
    install_request_id_middleware(app)
    install_cors_middleware(app, ("https://ogaforeman.example",))
    install_error_handlers(app)

    @app.get("/api/v1/projects")
    async def projects() -> dict[str, list[object]]:
        raise RuntimeError("database failure")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.get(
            "/api/v1/projects",
            headers={"Origin": "https://ogaforeman.example"},
        )
        denied = await client.get(
            "/api/v1/projects",
            headers={"Origin": "https://attacker.example"},
        )

    assert allowed.status_code == 500
    assert allowed.json()["error"]["code"] == "INTERNAL_ERROR"
    assert allowed.headers["access-control-allow-origin"] == "https://ogaforeman.example"
    assert "access-control-allow-origin" not in denied.headers
