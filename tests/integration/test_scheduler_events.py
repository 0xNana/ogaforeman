from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.config.settings import Settings
from app.domain.enums import AgentRunStatus, TaskStatus, WorkflowName
from app.domain.events import ProjectEvent
from app.domain.models import ActivityEvent, AgentRun, DailyReport, ProcessedEvent, Task
from app.infrastructure.pubsub import PubSubClient
from app.repositories.memory import InMemoryRepositoryStore
from app.worker_http import create_worker_app
from app.repositories.runs import run_id_for_event


class CapturingPublisher(PubSubClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.messages: list[bytes] = []

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        del topic, attributes
        self.messages.append(data)
        return f"msg_scheduler_{len(self.messages)}"


@pytest.mark.asyncio
async def test_scheduler_http_event_executes_one_durable_daily_brief() -> None:
    settings = Settings(_env_file=None, demo_mode=True)
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_scheduler123",
            project_id="prj_scheduler123",
            title="Ground-floor plumbing",
            status=TaskStatus.COMPLETED,
            completion_percent=Decimal("100"),
            actual_completion=datetime(2026, 8, 8, 4, 0, tzinfo=UTC),
        )
    )
    publisher = CapturingPublisher(settings)
    app = create_worker_app(
        settings=settings,
        store=store,
        publisher=publisher,
        clock=lambda: datetime(2026, 8, 8, 5, 30, tzinfo=UTC),
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        scheduled = await client.post(
            "/scheduler/daily-brief",
            json={"project_id": "prj_scheduler123", "timezone": "Africa/Accra"},
        )
        event = ProjectEvent.model_validate_json(publisher.messages[0])
        push = {
            "message": {
                "data": base64.b64encode(publisher.messages[0]).decode("ascii"),
                "messageId": scheduled.json()["message_id"],
            },
            "subscription": "projects/local/subscriptions/oga-worker",
        }
        first_delivery = await client.post("/pubsub/push", json=push)
        replay_delivery = await client.post("/pubsub/push", json=push)

    reports = store.repository(DailyReport).list("prj_scheduler123")
    runs = store.repository(AgentRun).list("prj_scheduler123")
    activities = store.repository(ActivityEvent).list("prj_scheduler123")

    assert scheduled.status_code == 202
    assert first_delivery.status_code == 204
    assert replay_delivery.status_code == 204
    assert len(reports) == 1
    assert reports[0].report_date.isoformat() == "2026-08-08"
    assert [fact.summary for fact in reports[0].completed_work] == [
        "Ground-floor plumbing completed."
    ]
    assert len(store.repository(ProcessedEvent).list("prj_scheduler123")) == 1
    assert len([item for item in activities if item.action == "daily_brief.generated"]) == 1
    assert len(runs) == 1
    assert runs[0].id == run_id_for_event(event.event_id)
    assert runs[0].workflow is WorkflowName.DAILY_BRIEF
    assert runs[0].status is AgentRunStatus.COMPLETED
