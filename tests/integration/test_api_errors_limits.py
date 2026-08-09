from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel

from app.api.dependencies import require_idempotency_key
from app.api.errors import (
    REQUEST_ID_HEADER,
    ApiError,
    install_error_handlers,
    install_request_id_middleware,
)
from app.api.limits import InMemoryRateLimiter, RateLimitExceededError
from app.domain.authorization import ProjectForbiddenError
from app.repositories.interfaces import VersionConflictError


class Payload(BaseModel):
    value: int


def make_app() -> FastAPI:
    app = FastAPI()
    install_request_id_middleware(app)
    install_error_handlers(app)

    @app.post("/mutate")
    async def mutate(payload: Payload, request: Request):
        require_idempotency_key(request)
        if payload.value == 403:
            raise ProjectForbiddenError("cross-project")
        if payload.value == 409:
            raise VersionConflictError("stale")
        if payload.value == 422:
            raise ApiError("APPROVAL_REQUIRED", "approval needed", status_code=422)
        return {"ok": True}

    @app.get("/explode")
    async def explode():
        raise RuntimeError("database password should not leak")

    return app


@pytest.mark.asyncio
async def test_error_envelope_request_id_and_stable_mapping() -> None:
    transport = httpx.ASGITransport(app=make_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/mutate",
            json={"value": 403},
            headers={"Idempotency-Key": "mutate:001", REQUEST_ID_HEADER: "req_client001"},
        )
        assert response.status_code == 403
        assert response.headers[REQUEST_ID_HEADER] == "req_client001"
        assert response.json() == {
            "error": {
                "code": "AUTH_PROJECT_FORBIDDEN",
                "message": "You do not have access to this project.",
                "request_id": "req_client001",
                "details": {},
            }
        }

        invalid = await client.post(
            "/mutate",
            json={"value": "bad"},
            headers={"Idempotency-Key": "mutate:002"},
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "VALIDATION_FAILED"
        assert invalid.json()["error"]["request_id"].startswith("req_")

        missing_key = await client.post("/mutate", json={"value": 1})
        assert missing_key.status_code == 400
        assert missing_key.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_unexpected_error_is_redacted_but_correlated() -> None:
    transport = httpx.ASGITransport(app=make_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/explode", headers={REQUEST_ID_HEADER: "req_explode001"})
        assert response.status_code == 500
        assert response.headers[REQUEST_ID_HEADER] == "req_explode001"
        assert response.json() == {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred.",
                "request_id": "req_explode001",
                "details": {},
            }
        }
        assert "password" not in response.text


def test_sliding_window_limits_user_project_and_ip_with_retry_header_data() -> None:
    limiter = InMemoryRateLimiter(
        user_limit=2,
        project_limit=10,
        ip_limit=10,
        window_seconds=60,
    )
    now = datetime(2026, 8, 7, 15, 0, tzinfo=UTC)

    first = limiter.check("usr_foreman", "prj_ridge", "127.0.0.1", now=now)
    second = limiter.check("usr_foreman", "prj_ridge", "127.0.0.1", now=now)
    assert first.remaining == 1
    assert second.remaining == 0

    try:
        limiter.check("usr_foreman", "prj_ridge", "127.0.0.1", now=now)
    except RateLimitExceededError as exc:
        assert exc.dimension == "user"
        assert exc.retry_after >= 1
    else:
        raise AssertionError("expected the third request to be rate limited")

    after_window = limiter.check(
        "usr_foreman", "prj_ridge", "127.0.0.1", now=datetime(2026, 8, 7, 15, 1, 1, tzinfo=UTC)
    )
    assert after_window.remaining == 1
