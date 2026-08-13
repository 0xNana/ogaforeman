"""Tests for approval workflow."""

from datetime import UTC, datetime

import pytest

from app.domain.authorization import ProjectAccessContext, AuthenticatedUser, RoleRequiredError
from app.domain.enums import (
    MemberRole,
    ActorType,
    ApprovalStatus,
    ApprovalActionType,
    AgentRunStatus,
    MaterialRequestStatus,
)
from app.domain.models import Approval, AgentRun, MaterialRequest, OutboxMessage, OutboxStatus
from app.repositories.interfaces import RepositorySession, RepositoryStore, VersionConflictError
from app.repositories.memory import InMemoryRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.workflows.resume import ResumeWorkflow
from app.domain.activity import MutationContext


@pytest.fixture
def store() -> RepositoryStore:
    return InMemoryRepositoryStore()


@pytest.fixture
def session(store: RepositoryStore) -> RepositorySession:
    return store


@pytest.fixture
def access() -> ProjectAccessContext:
    return ProjectAccessContext(
        project_id="prj_123",
        actor=AuthenticatedUser(user_id="usr_123", subject="sub_123", email="test@test.com"),
        role=MemberRole.MANAGER,
    )


@pytest.fixture
def setup_approvals(
    session: RepositorySession,
) -> None:
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


def test_approval_granted_and_resume(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_approvals: None,
) -> None:
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
        source_event_id="evt_1234567890_abc1",
    )

    result = service.approve(access, command, context)
    assert result.approval.status == ApprovalStatus.APPROVED
    assert result.activity is not None
    request = store.repository(MaterialRequest).require("prj_123", "req_123")
    assert request.status is MaterialRequestStatus.APPROVED

    # Simulate workflow event handler
    continuation = workflow.handle_approval_granted(
        project_id="prj_123",
        approval_id="app_123",
        resolver_id=access.actor.user_id,
    )
    assert continuation.run_id == "run_123"
    assert continuation.request_id == "req_123"

    # Check that run resumed
    runs = store.run_transaction(lambda s: list(s.repository(AgentRun).list("prj_123")))
    assert runs[0].status == AgentRunStatus.RUNNING


def test_approval_rejected_and_closes_request(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_approvals: None,
) -> None:
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
        source_event_id="evt_1234567890_abc2",
    )

    result = service.reject(access, command, context)
    assert result.approval.status == ApprovalStatus.REJECTED

    # Simulate workflow event handler
    workflow.handle_approval_rejected(
        project_id="prj_123",
        approval_id="app_123",
        resolver_id=access.actor.user_id,
    )

    # Check that request was cancelled
    reqs = store.run_transaction(lambda s: list(s.repository(MaterialRequest).list("prj_123")))
    assert reqs[0].status == MaterialRequestStatus.CANCELLED

    # Check that run failed
    runs = store.run_transaction(lambda s: list(s.repository(AgentRun).list("prj_123")))
    assert runs[0].status == AgentRunStatus.FAILED
    assert runs[0].error_code == "APPROVAL_REJECTED"


def test_approval_duplicate_decision(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_approvals: None,
) -> None:
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
        source_event_id="evt_1234567890_abc3",
    )

    result1 = service.approve(access, command, context)
    assert result1.approval.status == ApprovalStatus.APPROVED
    assert not result1.duplicate

    result2 = service.approve(access, command, context)
    assert result2.approval.status == ApprovalStatus.APPROVED
    assert result2.duplicate


class RecordingPublisher:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[tuple[str | None, bytes, dict[str, str] | None]] = []

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: dict[str, str] | None = None,
    ) -> str:
        self.calls.append((topic, data, attributes))
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("transient publish failure")
        return "msg_approval123"


def test_approval_publishes_persisted_continuation_outbox(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_approvals: None,
) -> None:
    publisher = RecordingPublisher()
    service = ApprovalService(store, publisher)
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
        idempotency_key="idemp_publish",
        source_event_id="evt_1234567890_publish",
    )

    service.approve(access, command, context)

    messages = store.repository(OutboxMessage).list("prj_123")
    assert len(messages) == 1
    assert messages[0].status is OutboxStatus.COMPLETED
    assert len(publisher.calls) == 1
    assert publisher.calls[0][2] == {
        "event_type": "APPROVAL_GRANTED",
        "project_id": "prj_123",
    }


def test_duplicate_approval_retries_failed_continuation_publish(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_approvals: None,
) -> None:
    publisher = RecordingPublisher(fail_first=True)
    service = ApprovalService(store, publisher)
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
        idempotency_key="idemp_retry_publish",
        source_event_id="evt_1234567890_retry",
    )

    first = service.approve(access, command, context)
    failed = store.repository(OutboxMessage).list("prj_123")[0]
    duplicate = service.approve(access, command, context)
    completed = store.repository(OutboxMessage).require("prj_123", failed.id)

    assert first.duplicate is False
    assert failed.status is OutboxStatus.FAILED
    assert duplicate.duplicate is True
    assert completed.status is OutboxStatus.COMPLETED
    assert completed.attempts == 2
    assert len(publisher.calls) == 2


def test_approval_conflict(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_approvals: None,
) -> None:
    service = ApprovalService(store)

    command = ResolutionCommand(
        project_id="prj_123",
        approval_id="app_123",
        notes="OK",
        expected_version=0,
    )

    context1 = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="idemp_4",
        source_event_id="evt_1234567890_abc4",
    )

    context2 = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="idemp_5",  # different idempotency key
        source_event_id="evt_1234567890_abc5",
    )

    # First approves
    service.approve(access, command, context1)

    # Second tries to reject using different context
    with pytest.raises(VersionConflictError):
        service.reject(access, command, context2)


def test_foreman_cannot_resolve_purchase_approval(
    store: RepositoryStore,
    setup_approvals: None,
) -> None:
    foreman_access = ProjectAccessContext(
        project_id="prj_123",
        actor=AuthenticatedUser(user_id="usr_foreman", subject="sub_foreman"),
        role=MemberRole.FOREMAN,
    )
    command = ResolutionCommand(
        project_id="prj_123",
        approval_id="app_123",
        expected_version=0,
    )
    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=foreman_access.actor.user_id,
        idempotency_key="foreman-approval-attempt",
        source_event_id="evt_foreman_attempt",
    )

    with pytest.raises(RoleRequiredError):
        ApprovalService(store).approve(foreman_access, command, context)
