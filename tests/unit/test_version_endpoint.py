"""Contract tests for public deployment provenance."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.router import api_router
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_version_endpoint_exposes_only_safe_immutable_build_identity() -> None:
    settings = Settings(
        _env_file=None,
        app_git_sha="b134039daa3bc1528f9e869678dd6d59a4f9d1f9",
        app_build_time="2026-08-23T14:05:06Z",
        app_version="0.1.0",
        app_source_tree_dirty=False,
        k_service="oga-api-staging",
        k_revision="oga-api-staging-00042-abc",
    )
    application = FastAPI()
    application.state.settings = settings
    application.include_router(api_router, prefix="/api/v1")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "app_version": "0.1.0",
        "git_sha": "b134039daa3bc1528f9e869678dd6d59a4f9d1f9",
        "build_timestamp": "2026-08-23T14:05:06Z",
        "source_tree_dirty": False,
        "environment": "local",
        "service": "oga-api-staging",
        "revision": "oga-api-staging-00042-abc",
    }


@pytest.mark.asyncio
async def test_version_endpoint_is_explicit_when_local_build_identity_is_absent() -> None:
    application = FastAPI()
    application.state.settings = Settings(_env_file=None)
    application.include_router(api_router, prefix="/api/v1")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/version")

    assert response.status_code == 200
    assert response.json()["git_sha"] is None
    assert response.json()["build_timestamp"] is None
    assert response.json()["source_tree_dirty"] is True
    assert response.json()["service"] is None
    assert response.json()["revision"] is None
