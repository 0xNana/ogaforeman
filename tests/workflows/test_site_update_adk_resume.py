from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.interpreter import FakeSiteInterpreter
from app.agents.site_update_execution import SiteUpdateEventExecutor
from app.config.settings import Settings
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    ProcessingStatus,
    SiteUpdateInputType,
    WorkflowName,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    MaterialRequest,
    OutboxMessage,
    ProjectMember,
    SiteUpdate,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.repositories.runs import run_id_for_event


_NOW = datetime(2026, 8, 3, 10, tzinfo=UTC)
_PROJECT_ID = "prj_adkresume123"
_FOREMAN_ID = "usr_adkforeman123"
_MANAGER_ID = "usr_adkmanager123"
_UPDATE_ID = "sup_adkresume123"
_SOURCE_EVENT_ID = "evt_adkresume123"
_RUN_ID = run_id_for_event(_SOURCE_EVENT_ID)
_APPROVAL_ID = "app_adkresume123"
_REQUEST_ID = "mrq_adkresume123"
_APP_NAME = "agents-ogaforeman-cloud-2026"
_SESSION_ID = f"{_RUN_ID}-attempt-1"


@pytest.mark.asyncio
async def test_purchase_approval_resumes_original_site_update_adk_session_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryRepositoryStore()
    approval_event = _seed_paused_approved_workflow(store)
    captured: dict[str, Any] = {}

    class FakeSessionService:
        async def get_session(self, **kwargs: Any) -> Any:
            captured["get_session"] = kwargs
            function_call = SimpleNamespace(id="approval-call-123", name="adk_request_input")
            return SimpleNamespace(
                events=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[SimpleNamespace(function_call=function_call)]
                        )
                    )
                ]
            )

    @asynccontextmanager
    async def managed_session_service(_settings: Settings) -> Any:
        yield FakeSessionService()

    @asynccontextmanager
    async def execution_guard(_settings: Settings) -> Any:
        yield

    def build_app(
        app_name: str,
        execute: Any,
        *,
        timeout_seconds: int,
    ) -> Any:
        captured["app_name"] = app_name
        captured["timeout_seconds"] = timeout_seconds
        return SimpleNamespace(name=app_name, execute=execute)

    class FakeRunner:
        def __init__(self, *, app: Any, session_service: Any, **_kwargs: Any) -> None:
            del session_service
            self._app = app

        async def run_async(self, **kwargs: Any) -> Any:
            captured["run_async"] = kwargs
            response = kwargs["new_message"].parts[0].function_response
            assert response.id == "approval-call-123"
            assert response.name == "adk_request_input"
            assert response.response["approval_id"] == _APPROVAL_ID
            yield SimpleNamespace(output=await self._app.execute())

    monkeypatch.setattr(
        "app.agents.site_update_execution.managed_session_service",
        managed_session_service,
    )
    monkeypatch.setattr(
        "app.agents.site_update_execution.sqlite_session_execution_guard",
        execution_guard,
    )
    monkeypatch.setattr("app.agents.site_update_execution.build_site_update_app", build_app)
    monkeypatch.setattr("app.agents.site_update_execution.Runner", FakeRunner)

    executor = SiteUpdateEventExecutor(
        store,
        FakeSiteInterpreter(responses={}),
        Settings(_env_file=None, agent_workflow_timeout_seconds=10),
    )
    result = await executor.resume_approved(approval_event)
    replay = await executor.resume_approved(approval_event)

    run = store.repository(AgentRun).require(_PROJECT_ID, _RUN_ID)
    update = store.repository(SiteUpdate).require(_PROJECT_ID, _UPDATE_ID)
    request = store.repository(MaterialRequest).require(_PROJECT_ID, _REQUEST_ID)
    activities = store.repository(ActivityEvent).list(_PROJECT_ID)
    assert result["run_id"] == _RUN_ID
    assert result["update_id"] == _UPDATE_ID
    assert replay["replayed"] is True
    assert captured["app_name"] == _APP_NAME
    assert captured["get_session"] == {
        "app_name": _APP_NAME,
        "user_id": _FOREMAN_ID,
        "session_id": _SESSION_ID,
    }
    assert captured["run_async"]["session_id"] == _SESSION_ID
    assert captured["run_async"]["invocation_id"] == _SOURCE_EVENT_ID
    assert run.status is AgentRunStatus.COMPLETED
    assert run.adk_session_id == f"{_APP_NAME}/{_SESSION_ID}"
    assert run.adk_invocation_id == _SOURCE_EVENT_ID
    assert run.adk_workflow_id == "daily_site_update_workflow"
    assert update.processing_status is ProcessingStatus.COMPLETED
    assert update.processed_at is not None
    assert request.status is MaterialRequestStatus.APPROVED
    for action in {
        "workflow.resumed",
        "site_update.processing_resumed",
        "site_update.processing_completed",
        "workflow.completed",
    }:
        assert sum(activity.action == action for activity in activities) == 1


def _seed_paused_approved_workflow(store: InMemoryRepositoryStore) -> ProjectEvent:
    submitted_at = _NOW - timedelta(minutes=5)
    decided_at = _NOW - timedelta(minutes=1)
    original_event = ProjectEvent(
        event_id=_SOURCE_EVENT_ID,
        project_id=_PROJECT_ID,
        event_type=EventType.SITE_UPDATE_RECEIVED,
        source=EventSource.WEB,
        occurred_at=submitted_at,
        received_at=submitted_at,
        actor=EventActor(type=EventActorType.USER, id=_FOREMAN_ID),
        idempotency_key="adk-resume-original-123",
        correlation_id=_SOURCE_EVENT_ID,
        payload={
            "site_update_id": _UPDATE_ID,
            "text": "We have 10 bags of cement left.",
            "transcript": None,
            "attachment_ids": [],
        },
    )
    approval_event = ProjectEvent(
        event_id="evt_adkapproval123",
        project_id=_PROJECT_ID,
        event_type=EventType.APPROVAL_GRANTED,
        source=EventSource.WEB,
        occurred_at=decided_at,
        received_at=decided_at,
        actor=EventActor(type=EventActorType.USER, id=_MANAGER_ID),
        idempotency_key="adk-resume-approval-123",
        correlation_id=_SOURCE_EVENT_ID,
        payload={
            "approval_id": _APPROVAL_ID,
            "resolver": _MANAGER_ID,
            "notes": "Approved after restart.",
        },
    )
    for model in (
        ProjectMember(
            project_id=_PROJECT_ID,
            user_id=_FOREMAN_ID,
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
            created_at=submitted_at,
            updated_at=submitted_at,
        ),
        SiteUpdate(
            id=_UPDATE_ID,
            project_id=_PROJECT_ID,
            submitted_by=_FOREMAN_ID,
            input_type=SiteUpdateInputType.TEXT,
            raw_text="We have 10 bags of cement left.",
            client_event_id="adk-resume-original-123",
            processing_status=ProcessingStatus.WAITING_FOR_APPROVAL,
            submitted_at=submitted_at,
            created_at=submitted_at,
            updated_at=submitted_at,
        ),
        AgentRun(
            id=_RUN_ID,
            project_id=_PROJECT_ID,
            trigger_event_id=_SOURCE_EVENT_ID,
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.WAITING_FOR_APPROVAL,
            step="approval_required",
            trace_id=_SOURCE_EVENT_ID,
            adk_session_id=f"{_APP_NAME}/{_SESSION_ID}",
            adk_invocation_id=_SOURCE_EVENT_ID,
            adk_workflow_id="daily_site_update_workflow",
            result_summary="Cement shortage requires approval.",
            pending_actions=["Review cement request."],
            started_at=submitted_at,
            updated_at=submitted_at,
        ),
        Approval(
            id=_APPROVAL_ID,
            project_id=_PROJECT_ID,
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_id": "mat_cement123", "quantity": "90"},
            reason="Cement shortage.",
            evidence_refs=[_SOURCE_EVENT_ID],
            status=ApprovalStatus.APPROVED,
            requested_by=_FOREMAN_ID,
            requested_at=submitted_at,
            resolved_at=decided_at,
            resolved_by=_MANAGER_ID,
            resolution_notes="Approved after restart.",
        ),
        MaterialRequest(
            id=_REQUEST_ID,
            project_id=_PROJECT_ID,
            material_id="mat_cement123",
            quantity=Decimal("90"),
            unit="bags",
            reason="Cement shortage.",
            source_event_id=_SOURCE_EVENT_ID,
            supplier="Golden supplier",
            status=MaterialRequestStatus.APPROVED,
            approval_id=_APPROVAL_ID,
            created_at=submitted_at,
            updated_at=decided_at,
        ),
        ActivityEvent(
            id="act_adksitereceived123",
            project_id=_PROJECT_ID,
            actor_type=ActorType.USER,
            actor_id=_FOREMAN_ID,
            action="site_update.received",
            entity_type="site_update",
            entity_id=_UPDATE_ID,
            summary="Received a site update.",
            source_event_id=_SOURCE_EVENT_ID,
            agent_run_id=_RUN_ID,
            created_at=submitted_at,
        ),
        OutboxMessage(
            id="obx_adksource123",
            project_id=_PROJECT_ID,
            message_type=EventType.SITE_UPDATE_RECEIVED.value,
            deduplication_key=original_event.idempotency_key,
            payload=original_event.model_dump(mode="json"),
            created_at=submitted_at,
        ),
    ):
        store.repository(type(model)).create(model)
    return approval_event
