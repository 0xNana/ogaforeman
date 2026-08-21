"""Production-readiness controls PR-01 through PR-13.

Strict expected failures are deliberate release blockers. They make missing
prerequisite behavior visible without misreporting the Phase 8 harness itself as
broken. An unexpected pass fails the suite so the marker must be removed when the
underlying control is implemented.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from google.cloud import firestore
from pydantic import ValidationError

from app.agents.interpreter import FakeSiteInterpreter
from app.agents.registry import Registry
from app.config.settings import Settings
from app.api.limits import InMemoryRateLimiter, RateLimitExceededError
from app.api.v1.router import api_router
from app.domain.activity import MutationContext
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectForbiddenError,
    RoleRequiredError,
)
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    TaskStatus,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.facts import ConfidenceLevel, ExtractedFactSet, TaskCompletionFact
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Material,
    MaterialRequest,
    Issue,
    OutboxMessage,
    ProcessedEvent,
    ProjectMember,
    ReportFact,
    SiteUpdate,
    Task,
)
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.interfaces import RepositoryStore
from app.repositories.memory import InMemoryRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.services.entity_resolution import MatchConfidence, resolve_task
from app.services.fact_router import route_facts
from app.services.materials import MaterialService
from app.services.reports import ReportService
from app.services.site_update_intake import SiteUpdateIntakeService
from app.services.tasks import TaskService, UpdateTaskCommand
from app.worker import process_event, process_event_async


ROOT = Path(__file__).resolve().parents[2]


def _event_bytes() -> bytes:
    event = ProjectEvent(
        event_id="evt_readiness123",
        project_id="prj_readiness123",
        event_type=EventType.TASK_COMPLETED,
        source=EventSource.WEB,
        occurred_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        received_at=datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        actor=EventActor(type=EventActorType.USER, id="usr_foreman123"),
        idempotency_key="readiness:event:123",
        correlation_id="cor_readiness123",
        payload={"task_id": "tsk_blockwork123", "evidence_refs": ["manual-test"]},
    )
    return event.model_dump_json().encode("utf-8")


def _manager_access(project_id: str = "prj_readiness123") -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="sub_manager123"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )


def _approval_state(store: RepositoryStore) -> None:
    store.repository(Approval).create(
        Approval(
            id="app_purchase123",
            project_id="prj_readiness123",
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_id": "mat_cement123", "quantity": "100"},
            reason="Cement is required for tomorrow's plastering.",
            requested_by="system",
        )
    )
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id="prj_readiness123",
            material_id="mat_cement123",
            quantity=Decimal("100"),
            unit="bags",
            reason="Cement is required for tomorrow's plastering.",
            supplier="Delayed Logistics",
            source_event_id="evt_shortage123",
            status=MaterialRequestStatus.PROPOSED,
            approval_id="app_purchase123",
        )
    )
    store.repository(AgentRun).create(
        AgentRun(
            id="run_material123",
            project_id="prj_readiness123",
            trigger_event_id="evt_shortage123",
            workflow="material_shortage",
            status=AgentRunStatus.WAITING_FOR_APPROVAL,
            trace_id="trc_material123",
            adk_session_id="ses_123",
            adk_invocation_id="inv_123",
        )
    )


def _approval_context(key: str) -> MutationContext:
    return MutationContext(
        project_id="prj_readiness123",
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        source_event_id="evt_decision123",
        idempotency_key=key,
    )


def test_pr01_production_paths_have_no_process_global_project_database() -> None:
    production_files = [ROOT / "main.py", *sorted((ROOT / "app").rglob("*.py"))]
    source = "\n".join(path.read_text(encoding="utf-8") for path in production_files)
    runtime_files = [
        path for path in production_files if path != ROOT / "app" / "repositories" / "memory.py"
    ]

    assert "_PROJECT_DB" not in source
    assert "datetime.utcnow" not in source
    assert all(
        "InMemoryRepositoryStore(" not in path.read_text(encoding="utf-8") for path in runtime_files
    )


def test_pr02_duplicate_event_and_report_fact_are_suppressed() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_readiness123",
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id="prj_readiness123",
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        )
    )
    first = process_event(_event_bytes(), store=store)
    replay = process_event(_event_bytes(), store=store)
    reports = ReportService(store)
    fact = ReportFact(summary="Blockwork completed", source_refs=["sup_readiness123"])
    reports.append_fact(
        "prj_readiness123",
        datetime(2026, 8, 8, tzinfo=UTC).date(),
        fact,
        "completed_work",
        "sup_readiness123",
    )
    report = reports.append_fact(
        "prj_readiness123",
        datetime(2026, 8, 8, tzinfo=UTC).date(),
        fact,
        "completed_work",
        "sup_readiness123",
    )

    assert first.status == "completed"
    assert replay.status == "duplicate"
    assert len(store.repository(ProcessedEvent).list("prj_readiness123")) == 1
    assert len(report.completed_work) == 1


def test_pr03_rejection_atomically_closes_linked_request() -> None:
    store = InMemoryRepositoryStore()
    _approval_state(store)

    result = ApprovalService(store).reject(
        _manager_access(),
        ResolutionCommand(
            project_id="prj_readiness123",
            approval_id="app_purchase123",
            expected_version=0,
            notes="Use a smaller order.",
        ),
        _approval_context("readiness:reject:123"),
    )
    request = store.repository(MaterialRequest).require(
        "prj_readiness123",
        "mrq_cement123",
    )

    assert result.approval.status is ApprovalStatus.REJECTED
    assert request.status in {MaterialRequestStatus.REJECTED, MaterialRequestStatus.CANCELLED}


@pytest.mark.backing_services
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for PR-04 restart verification",
)
def test_pr04_approval_event_resumes_persisted_run_after_restart() -> None:
    firestore_project = f"oga-readiness-{uuid4().hex}"
    store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    _approval_state(store)
    ApprovalService(store).approve(
        _manager_access(),
        ResolutionCommand(
            project_id="prj_readiness123",
            approval_id="app_purchase123",
            expected_version=0,
        ),
        _approval_context("readiness:approve:123"),
    )
    outbox = store.repository(OutboxMessage).list("prj_readiness123")
    continuation = next(message for message in outbox if message.message_type == "APPROVAL_GRANTED")

    continuation_event = ProjectEvent.model_validate(continuation.payload)
    restarted_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    process_event(
        continuation_event.model_dump_json().encode(),
        store=restarted_store,
    )
    replay = process_event(
        continuation_event.model_dump_json().encode(),
        store=restarted_store,
    )
    final_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    run = final_store.repository(AgentRun).require(
        "prj_readiness123",
        "run_material123",
    )

    request = final_store.repository(MaterialRequest).require(
        "prj_readiness123",
        "mrq_cement123",
    )
    processed = final_store.repository(ProcessedEvent).list("prj_readiness123")
    actions = final_store.repository(OutboxMessage).list("prj_readiness123")

    assert replay.status == "duplicate"
    assert run.status is AgentRunStatus.COMPLETED
    assert request.status is MaterialRequestStatus.DELAYED
    assert len(final_store.repository(Issue).list("prj_readiness123")) == 1
    assert {item.event_type for item in processed} == {
        EventType.APPROVAL_GRANTED.value,
        EventType.DELIVERY_DELAYED.value,
    }
    assert any(
        item.message_type == "supplier:submit_material_request" and item.status.value == "completed"
        for item in actions
    )


def test_pr05_material_aliases_resolve_to_one_canonical_identity() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id="prj_readiness123",
            name="Cement Bags",
            normalized_name="cement bags",
            aliases=["portland cement"],
            unit="bags",
            available_quantity=Decimal("10"),
        )
    )
    service = MaterialService(store)

    assert service.resolve_material(_manager_access(), "Cement Bags").id == "mat_cement123"
    assert service.resolve_material(_manager_access(), "cement bags").id == "mat_cement123"
    assert service.resolve_material(_manager_access(), "portland cement").id == "mat_cement123"


def test_pr06_naive_datetimes_and_utcnow_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Task(
            id="tsk_naive123",
            project_id="prj_readiness123",
            title="Naive timestamp",
            planned_start=datetime(2026, 8, 8, 10, 0),
        )

    production_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "app").rglob("*.py"))
    )
    assert "datetime.utcnow" not in production_source


def test_pr07_task_resolution_uses_authorized_context_and_clarifies_ambiguity() -> None:
    tasks = [
        Task(
            id="tsk_north_wall123",
            project_id="prj_readiness123",
            title="North retaining wall",
        ),
        Task(
            id="tsk_north_finish123",
            project_id="prj_readiness123",
            title="North wall finish",
        ),
    ]

    exact = resolve_task("North retaining wall", tasks)
    ambiguous = resolve_task("North", tasks)
    unknown = resolve_task("Roof membrane", tasks)

    assert exact.confidence is MatchConfidence.HIGH
    assert exact.resolved_entity is not None
    assert ambiguous.confidence is MatchConfidence.AMBIGUOUS
    assert unknown.confidence is MatchConfidence.UNKNOWN


def test_pr08_negated_completion_never_becomes_actionable_progress() -> None:
    routed = route_facts(
        ExtractedFactSet(
            tasks=[
                TaskCompletionFact(
                    task_name="Electrical rough-in",
                    is_completed=False,
                    is_negated=True,
                    evidence="The electrician did not come today.",
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
    )

    assert routed.actionable_tasks == []
    assert len(routed.observations) == 1


@pytest.mark.asyncio
async def test_pr09_api_site_update_enters_the_worker_coordinator_path() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_readiness123",
            user_id="usr_manager123",
            role=MemberRole.MANAGER,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id="prj_readiness123",
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        )
    )
    published: list[bytes] = []

    def publish(
        topic: str | None,
        data: bytes,
        *,
        attributes: dict[str, str] | None = None,
    ) -> str:
        del topic, attributes
        published.append(data)
        return "message:accepted"

    app = FastAPI()
    app.state.project_access_provider = lambda request, project_id, permission: _manager_access(
        project_id
    )
    app.state.site_update_intake = SiteUpdateIntakeService(
        store,
        SimpleNamespace(publish=publish),
    )
    app.include_router(api_router, prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects/prj_readiness123/site-updates",
            json={"text": "Blockwork is complete."},
            headers={"Idempotency-Key": "readiness:site-update:123"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert len(published) == 1
    event = ProjectEvent.model_validate_json(published[0])
    interpreter = FakeSiteInterpreter(
        responses={
            "Blockwork is complete.": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="Blockwork",
                        is_completed=True,
                        evidence="Blockwork is complete.",
                        confidence=ConfidenceLevel.HIGH,
                    )
                ]
            )
        }
    )
    worker_result = await process_event_async(
        published[0],
        store=store,
        settings=Settings(_env_file=None),
        site_interpreter=interpreter,
    )
    run = store.repository(AgentRun).require(
        "prj_readiness123",
        response.json()["agent_run_id"],
    )
    assert event.event_type is EventType.SITE_UPDATE_RECEIVED
    assert worker_result.result_ref == f"run:{run.id}"
    assert run.status is AgentRunStatus.COMPLETED
    assert (
        store.repository(Task).require("prj_readiness123", "tsk_blockwork123").status
        is TaskStatus.COMPLETED
    )
    assert len(store.repository(SiteUpdate).list("prj_readiness123")) == 1
    assert len(store.repository(AgentRun).list("prj_readiness123")) == 1


def test_pr10_agent_registry_resolves_every_coordinator_route() -> None:
    registry = Registry()
    coordinator = registry.get_agent_config("oga_coordinator")

    assert len(coordinator.sub_agents) == len(set(coordinator.sub_agents))
    for route in coordinator.sub_agents:
        assert registry.get_agent_config(route).name == route


def test_pr11_task_mutation_emits_exactly_one_activity() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id="prj_readiness123",
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        )
    )
    context = MutationContext(
        project_id="prj_readiness123",
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        source_event_id="evt_progress123",
        agent_run_id="run_progress123",
        idempotency_key="readiness:task:complete:123",
    )
    command = UpdateTaskCommand(
        project_id="prj_readiness123",
        task_id="tsk_blockwork123",
        expected_version=0,
        completion_percent=Decimal("100"),
        evidence="First-floor blockwork is done.",
    )

    TaskService(store).complete_task(_manager_access(), command, context)
    activities = store.repository(ActivityEvent).list("prj_readiness123")

    assert len(activities) == 1
    assert activities[0].source_event_id == "evt_progress123"
    assert activities[0].agent_run_id == "run_progress123"


def test_pr12_project_authorization_and_rate_limits_fail_closed() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_secure123",
            project_id="prj_readiness123",
            title="Secure task",
            status=TaskStatus.IN_PROGRESS,
        )
    )
    viewer = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_viewer123", subject="sub_viewer123"),
        project_id="prj_readiness123",
        role=MemberRole.VIEWER,
    )
    command = UpdateTaskCommand(
        project_id="prj_readiness123",
        task_id="tsk_secure123",
        expected_version=0,
        completion_percent=Decimal("50"),
        evidence="Half complete.",
    )
    context = MutationContext(
        project_id="prj_readiness123",
        actor_type=ActorType.USER,
        actor_id="usr_viewer123",
        source_event_id="evt_secure123",
        idempotency_key="readiness:secure:123",
    )

    with pytest.raises(RoleRequiredError):
        TaskService(store).update_task(viewer, command, context)
    with pytest.raises(ProjectForbiddenError):
        TaskService(store).update_task(
            viewer,
            command.model_copy(update={"project_id": "prj_other123"}),
            context,
        )

    limiter = InMemoryRateLimiter(
        user_limit=1,
        project_limit=2,
        ip_limit=2,
        window_seconds=60,
    )
    limiter.check("usr_viewer123", "prj_readiness123", "127.0.0.1")
    with pytest.raises(RateLimitExceededError):
        limiter.check("usr_viewer123", "prj_readiness123", "127.0.0.1")


def test_pr13_frontend_demo_state_is_explicit_and_production_fails_closed() -> None:
    api_source = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    report_source = (
        ROOT / "frontend" / "app" / "projects" / "[id]" / "reports" / "page.tsx"
    ).read_text(encoding="utf-8")

    assert "demoSnapshot" not in api_source
    assert "demoApi" not in api_source
    assert "NEXT_PUBLIC_DEMO_MODE" not in api_source
    assert "Ridge House" not in report_source
    assert "project.name" in report_source
    assert "ApiConfigurationError" in api_source
    assert "return result ??" not in api_source
    assert "if (!baseUrl) return null" not in api_source
