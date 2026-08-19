from __future__ import annotations

import base64
from datetime import UTC, datetime

import httpx
import pytest

from app.agents.interpreter import FakeSiteInterpreter
from app.config.settings import Settings
from app.domain.enums import (
    AgentRunStatus,
    MemberRole,
    MemberStatus,
    SiteUpdateInputType,
    WorkflowName,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import AgentRun, ProcessedEvent, ProjectMember, SiteUpdate
from app.infrastructure.pubsub import PubSubClient
from app.repositories.memory import InMemoryRepositoryStore
from app.worker_http import create_worker_app
from app.repositories.runs import run_id_for_event


def _event_bytes() -> bytes:
    now = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
    event = ProjectEvent(
        event_id="evt_httpworker123",
        project_id="prj_httpworker123",
        event_type=EventType.SITE_UPDATE_RECEIVED,
        source=EventSource.WEB,
        occurred_at=now,
        received_at=now,
        actor=EventActor(type=EventActorType.USER, id="usr_foreman123"),
        idempotency_key="worker-http:event:123",
        correlation_id="cor_httpworker123",
        payload={
            "site_update_id": "upd_httpworker123",
            "text": "Blockwork is complete.",
            "attachment_ids": [],
        },
    )
    return event.model_dump_json().encode()


@pytest.mark.asyncio
async def test_pubsub_push_invokes_idempotent_worker_path() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_httpworker123",
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(SiteUpdate).create(
        SiteUpdate(
            id="upd_httpworker123",
            project_id="prj_httpworker123",
            submitted_by="usr_foreman123",
            input_type=SiteUpdateInputType.TEXT,
            raw_text="Blockwork is complete.",
            client_event_id="worker-http-event-123",
            submitted_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        )
    )
    store.repository(AgentRun).create(
        AgentRun(
            id=run_id_for_event("evt_httpworker123"),
            project_id="prj_httpworker123",
            trigger_event_id="evt_httpworker123",
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.QUEUED,
            trace_id="cor_httpworker123",
        )
    )
    interpreter = FakeSiteInterpreter()
    app = create_worker_app(
        settings=Settings(_env_file=None, demo_mode=True),
        store=store,
        site_interpreter=interpreter,
    )
    payload = {
        "message": {
            "data": base64.b64encode(_event_bytes()).decode("ascii"),
            "messageId": "message-123",
        },
        "subscription": "projects/local/subscriptions/oga-worker",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/pubsub/push", json=payload)
        replay = await client.post("/pubsub/push", json=payload)

    assert first.status_code == 204
    assert replay.status_code == 204
    assert len(store.repository(ProcessedEvent).list("prj_httpworker123")) == 1
    assert interpreter.calls == ["Blockwork is complete."]


@pytest.mark.asyncio
async def test_scheduler_publishes_one_stable_daily_brief_event() -> None:
    settings = Settings(_env_file=None, demo_mode=True)
    publisher = PubSubClient(settings)
    app = create_worker_app(
        settings=settings,
        store=InMemoryRepositoryStore(),
        publisher=publisher,
        clock=lambda: datetime(2026, 8, 8, 5, 30, tzinfo=UTC),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scheduler/daily-brief",
            json={"project_id": "prj_ridge", "timezone": "Africa/Accra"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.json()["message_id"].startswith("msg_demo_")
