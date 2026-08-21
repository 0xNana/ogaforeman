from __future__ import annotations

from datetime import UTC, datetime

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
from app.repositories.memory import InMemoryRepositoryStore
from app.worker import process_event
from app.repositories.runs import run_id_for_event


def event_bytes() -> bytes:
    event = ProjectEvent(
        event_id="evt_worker123",
        project_id="prj_worker123",
        event_type=EventType.SITE_UPDATE_RECEIVED,
        source=EventSource.WEB,
        occurred_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        received_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        actor=EventActor(type=EventActorType.USER, id="usr_foreman123"),
        idempotency_key="worker:event:123",
        correlation_id="cor_worker123",
        payload={
            "site_update_id": "sup_worker123",
            "text": "Blockwork is complete.",
            "attachment_ids": [],
        },
    )
    return event.model_dump_json().encode("utf-8")


def test_worker_claims_routes_and_suppresses_duplicate_delivery() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_worker123",
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(SiteUpdate).create(
        SiteUpdate(
            id="sup_worker123",
            project_id="prj_worker123",
            submitted_by="usr_foreman123",
            input_type=SiteUpdateInputType.TEXT,
            raw_text="Blockwork is complete.",
            client_event_id="worker-event-123",
            submitted_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        )
    )
    store.repository(AgentRun).create(
        AgentRun(
            id=run_id_for_event("evt_worker123"),
            project_id="prj_worker123",
            trigger_event_id="evt_worker123",
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.QUEUED,
            trace_id="cor_worker123",
        )
    )
    interpreter = FakeSiteInterpreter()
    settings = Settings(_env_file=None)
    first = process_event(
        event_bytes(), store=store, settings=settings, site_interpreter=interpreter
    )
    replay = process_event(
        event_bytes(), store=store, settings=settings, site_interpreter=interpreter
    )

    assert first.status == "completed"
    assert first.route == "site_report"
    assert replay.status == "duplicate"
    assert replay.result_ref == first.result_ref
    assert interpreter.calls == ["Blockwork is complete."]
    assert len(store.repository(ProcessedEvent).list("prj_worker123")) == 1


def test_worker_persists_failed_claim_without_exposing_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryRepositoryStore()

    async def fail(*_args, **_kwargs):
        raise RuntimeError("deliberate worker failure")

    monkeypatch.setattr("app.agents.site_update_execution.SiteUpdateEventExecutor.execute", fail)
    settings = Settings(_env_file=None)
    interpreter = FakeSiteInterpreter()
    with pytest.raises(RuntimeError, match="deliberate worker failure"):
        process_event(event_bytes(), store=store, settings=settings, site_interpreter=interpreter)

    processed = store.repository(ProcessedEvent).list("prj_worker123")
    assert len(processed) == 1
    assert processed[0].status.value == "failed"
    assert processed[0].claim_token is None
