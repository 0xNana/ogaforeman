from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.cors import install_cors_middleware


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
