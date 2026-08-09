from __future__ import annotations

import json
import logging
from io import StringIO

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_request_id_middleware
from app.api.health import router as health_router
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.observability.dead_letters import DeadLetterService
from app.observability.logging import JsonLogFormatter
from app.repositories.memory import InMemoryRepositoryStore
from app.services.event_claims import EventClaimService


@pytest.mark.asyncio
async def test_request_logs_and_response_share_request_and_correlation_ids() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("ogaforeman.api")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    app = FastAPI()
    install_request_id_middleware(app)
    app.include_router(health_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health/live",
            headers={"X-Request-ID": "req_health123", "X-Correlation-ID": "cor_health123"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req_health123"
    assert response.headers["X-Correlation-ID"] == "cor_health123"
    record = json.loads(stream.getvalue())
    assert record["request_id"] == "req_health123"
    assert record["correlation_id"] == "cor_health123"
    assert record["event"] == "http_request_finished"


def test_dead_letter_inspection_is_project_scoped_and_redacts_claim_tokens() -> None:
    store = InMemoryRepositoryStore()
    claims = EventClaimService(store, max_attempts=1)
    now = "2026-08-08T10:00:00+00:00"
    event = ProjectEvent(
        event_id="evt_deadletter123",
        project_id="prj_deadletter123",
        event_type=EventType.SITE_UPDATE_RECEIVED,
        source=EventSource.WEB,
        occurred_at=now,
        received_at=now,
        actor=EventActor(type=EventActorType.USER, id="usr_foreman123"),
        idempotency_key="dead-letter:123",
        correlation_id="cor_deadletter123",
        payload={
            "site_update_id": "sup_deadletter123",
            "text": "Blockwork is complete.",
            "transcript": None,
            "attachment_ids": [],
        },
    )
    claimed = claims.claim(event)
    assert claimed.claim_token is not None
    claims.fail(
        event,
        claim_token=claimed.claim_token,
        error_code="TEST_FAILURE",
        error_summary="deliberate test failure",
    )

    service = DeadLetterService(store)
    events = service.list("prj_deadletter123")
    assert len(events) == 1
    assert events[0].claim_token is None
    assert service.list("prj_otherproject123") == ()
