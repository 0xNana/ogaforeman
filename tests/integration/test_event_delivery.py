import httpx
import pytest
from fastapi import FastAPI

from app.api.events import create_event_router
from app.config.settings import Settings
from app.infrastructure.pubsub import PubSubClient


@pytest.mark.asyncio
async def test_event_delivery() -> None:
    app = FastAPI()
    app.include_router(
        create_event_router(
            PubSubClient(Settings(_env_file=None, demo_mode=True)),
            authorize=lambda _request: None,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events/",
            json={
                "event_id": "evt_123456789012_abc123",
                "project_id": "proj_123456789012_abc123",
                "event_type": "TASK_COMPLETED",
                "source": "system",
                "occurred_at": "2026-08-08T00:00:00Z",
                "received_at": "2026-08-08T00:00:00Z",
                "actor": {"type": "system", "id": "sys_123456789012_abc123"},
                "idempotency_key": "idemp_123",
                "correlation_id": "corr_123456789012_abc123",
                "payload": {
                    "task_id": "task_123456789012_abc123",
                    "evidence_refs": [],
                },
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_generic_event_boundary_rejects_delivery_delay_injection() -> None:
    app = FastAPI()
    app.include_router(
        create_event_router(
            PubSubClient(Settings(_env_file=None, demo_mode=True)),
            authorize=lambda _request: None,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events/",
            json={
                "event_id": "evt_deliveryboundary123",
                "project_id": "prj_deliveryboundary123",
                "event_type": "DELIVERY_DELAYED",
                "source": "integration",
                "occurred_at": "2026-08-08T00:00:00Z",
                "received_at": "2026-08-08T00:00:00Z",
                "actor": {"type": "integration", "id": "int_deliveryboundary123"},
                "idempotency_key": "delivery-boundary-123",
                "correlation_id": "cor_deliveryboundary123",
                "payload": {
                    "request_id": "mrq_deliveryboundary123",
                    "new_date": "2026-08-12",
                    "reason": "Reported delay.",
                },
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == ("delivery delays require the authenticated project intake")
