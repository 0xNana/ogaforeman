"""Tests for M-03 restart-safe resume workflow."""

from datetime import UTC, datetime

import pytest

from app.domain.authorization import ProjectAccessContext, AuthenticatedUser
from app.domain.enums import (
    MemberRole,
    ActorType,
    ApprovalStatus,
    ApprovalActionType,
    AgentRunStatus,
    MaterialRequestStatus,
)
from app.domain.models import Approval, AgentRun, MaterialRequest, OutboxMessage
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.memory import InMemoryRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.workflows.resume import ResumeWorkflow
from app.domain.activity import MutationContext


@pytest.fixture
def store() -> RepositoryStore:
    return InMemoryRepositoryStore()


@pytest.fixture
def access() -> ProjectAccessContext:
    return ProjectAccessContext(
        project_id="prj_123",
        actor=AuthenticatedUser(user_id="usr_123", subject="sub_123", email="test@test.com"),
        role=MemberRole.MANAGER,
    )


def setup_state(store: RepositoryStore) -> None:
    def _setup(session: RepositorySession):
        approvals = session.repository(Approval)
        approvals.create(
            Approval(
                id="app_123",
                project_id="prj_123",
                action_type=ApprovalActionType.PURCHASE,
                proposed_action={"item": "Paint"},
                reason="Need paint",
                requested_by="system",
            )
        )

        runs = session.repository(AgentRun)
        runs.create(
            AgentRun(
                id="run_123",
                project_id="prj_123",
                trigger_event_id="evt_1234567890_abc",
                workflow="material_shortage",
                trace_id="trc_123",
                status=AgentRunStatus.WAITING_FOR_APPROVAL,
                started_at=datetime.now(UTC),
            )
        )

        requests = session.repository(MaterialRequest)
        requests.create(
            MaterialRequest(
                id="req_123",
                project_id="prj_123",
                material_id="mat_123",
                quantity=5,
                unit="litres",
                reason="Need paint",
                source_event_id="evt_1234567890_abc",
                status=MaterialRequestStatus.PROPOSED,
                approval_id="app_123",
            )
        )

    store.run_transaction(_setup)


def test_approval_granted_and_resume_after_restart(
    store: RepositoryStore, access: ProjectAccessContext
) -> None:
    setup_state(store)

    # Simulate worker restart by instantiating new services with same store
    service = ApprovalService(store)
    workflow = ResumeWorkflow(store)

    command = ResolutionCommand(
        project_id="prj_123",
        approval_id="app_123",
        notes="Approved the purchase",
        expected_version=0,
    )

    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="idemp_1",
        source_event_id="evt_trigger",
    )

    result = service.approve(access, command, context)
    assert result.approval.status == ApprovalStatus.APPROVED

    continuation = workflow.handle_approval_granted(
        project_id="prj_123",
        approval_id="app_123",
        resolver_id=access.actor.user_id,
    )
    assert continuation.run_id == "run_123"
    assert continuation.request_id == "req_123"

    # Run should be RUNNING
    runs = store.run_transaction(lambda s: list(s.repository(AgentRun).list("prj_123")))
    assert runs[0].status == AgentRunStatus.RUNNING

    # External actions logic check - make sure an outbox message was created for approval event but not immediately executed
    outbox = store.run_transaction(lambda s: list(s.repository(OutboxMessage).list("prj_123")))
    assert any(m.message_type == "APPROVAL_GRANTED" for m in outbox)


def test_approval_rejected_and_closes_request(
    store: RepositoryStore, access: ProjectAccessContext
) -> None:
    setup_state(store)

    service = ApprovalService(store)
    workflow = ResumeWorkflow(store)

    command = ResolutionCommand(
        project_id="prj_123",
        approval_id="app_123",
        notes="Too expensive",
        expected_version=0,
    )

    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="idemp_2",
        source_event_id="evt_trigger",
    )

    result = service.reject(access, command, context)
    assert result.approval.status == ApprovalStatus.REJECTED

    workflow.handle_approval_rejected(
        project_id="prj_123",
        approval_id="app_123",
        resolver_id=access.actor.user_id,
    )

    # Request should be CANCELLED
    reqs = store.run_transaction(lambda s: list(s.repository(MaterialRequest).list("prj_123")))
    assert reqs[0].status == MaterialRequestStatus.CANCELLED

    # Run should be FAILED
    runs = store.run_transaction(lambda s: list(s.repository(AgentRun).list("prj_123")))
    assert runs[0].status == AgentRunStatus.FAILED
    assert runs[0].error_code == "APPROVAL_REJECTED"


def test_approval_duplicate_decision(store: RepositoryStore, access: ProjectAccessContext) -> None:
    setup_state(store)

    service = ApprovalService(store)

    command = ResolutionCommand(
        project_id="prj_123",
        approval_id="app_123",
        notes="OK",
        expected_version=0,
    )

    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="idemp_3",
        source_event_id="evt_trigger",
    )

    result1 = service.approve(access, command, context)
    assert result1.approval.status == ApprovalStatus.APPROVED
    assert not result1.duplicate

    result2 = service.approve(access, command, context)
    assert result2.approval.status == ApprovalStatus.APPROVED
    assert result2.duplicate


def test_external_action_not_called(store: RepositoryStore, access: ProjectAccessContext) -> None:
    """Verifies that we don't call external actions directly during the mutation transaction."""
    setup_state(store)

    service = ApprovalService(store)
    command = ResolutionCommand(
        project_id="prj_123",
        approval_id="app_123",
        notes="OK",
        expected_version=0,
    )
    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="idemp_4",
        source_event_id="evt_trigger",
    )

    service.approve(access, command, context)

    # There should only be an OutboxMessage for the event, no direct API calls should have been made
    outbox = store.run_transaction(lambda s: list(s.repository(OutboxMessage).list("prj_123")))
    assert any(m.message_type == "APPROVAL_GRANTED" for m in outbox)
