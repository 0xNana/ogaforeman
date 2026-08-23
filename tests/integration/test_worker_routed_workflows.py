from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.activity import MutationContext
from app.config.settings import Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    IssueDetectedBy,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    TaskStatus,
    TaskSource,
    WorkflowName,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    ProcessedEvent,
    Project,
    ProjectMember,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.worker import process_event
from app.repositories.runs import run_id_for_event
from tests.fakes import FakeProjectNotificationGateway


NOW = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
PROJECT_ID = "prj_routed123"
FOREMAN_ID = "usr_foreman123"


def _store(*, with_member: bool = True) -> InMemoryRepositoryStore:
    store = InMemoryRepositoryStore()
    if with_member:
        store.repository(ProjectMember).create(
            ProjectMember(
                project_id=PROJECT_ID,
                user_id=FOREMAN_ID,
                role=MemberRole.FOREMAN,
                status=MemberStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return store


def _event(
    event_id: str,
    event_type: EventType,
    payload: dict[str, object],
    *,
    source: EventSource = EventSource.WEB,
    actor_type: EventActorType = EventActorType.USER,
    actor_id: str = FOREMAN_ID,
    project_id: str = PROJECT_ID,
    idempotency_key: str | None = None,
) -> ProjectEvent:
    return ProjectEvent(
        event_id=event_id,
        project_id=project_id,
        event_type=event_type,
        source=source,
        occurred_at=NOW,
        received_at=NOW,
        actor=EventActor(type=actor_type, id=actor_id),
        idempotency_key=idempotency_key or f"worker:{event_type.value.lower()}:{event_id}",
        correlation_id=f"cor_{event_id.removeprefix('evt_')}",
        payload=payload,
    )


def _deliver(
    store: InMemoryRepositoryStore,
    event: ProjectEvent,
    *,
    notification_gateway: FakeProjectNotificationGateway | None = None,
) -> tuple[str, str]:
    settings = Settings(_env_file=None, oga_env="test", use_fake_model=True)
    first = process_event(
        event.model_dump_json().encode(),
        store=store,
        settings=settings,
        notification_gateway=notification_gateway,
    )
    replay = process_event(
        event.model_dump_json().encode(),
        store=store,
        settings=settings,
        notification_gateway=notification_gateway,
    )
    assert replay.status == "duplicate"
    assert replay.result_ref == first.result_ref
    return first.status, first.result_ref or ""


def test_task_completed_event_mutates_task_and_completes_a_durable_run() -> None:
    store = _store()
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id=PROJECT_ID,
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
            actual_start=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    event = _event(
        "evt_taskcomplete123",
        EventType.TASK_COMPLETED,
        {
            "task_id": "tsk_blockwork123",
            "evidence_refs": ["site-log-123"],
            "completion_percent": 100,
        },
    )

    status, result_ref = _deliver(store, event)

    task = store.repository(Task).require(PROJECT_ID, "tsk_blockwork123")
    run = store.repository(AgentRun).require(PROJECT_ID, run_id_for_event(event.event_id))
    activities = store.repository(ActivityEvent).list(PROJECT_ID)
    assert status == "completed"
    assert result_ref == "task:tsk_blockwork123"
    assert task.status is TaskStatus.COMPLETED
    assert task.completion_percent == Decimal("100")
    assert run.workflow is WorkflowName.DAILY_SITE_UPDATE
    assert run.status is AgentRunStatus.COMPLETED
    assert [activity.action for activity in activities] == [
        "task.completed",
        "agent_run.completed",
        "agent_run.started",
    ]


def test_material_events_create_and_observe_one_approval_gated_request() -> None:
    store = _store()
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement Bags",
            normalized_name="cement bags",
            unit="bags",
            available_quantity=Decimal("5"),
            minimum_required_quantity=Decimal("20"),
            updated_at=NOW,
        )
    )
    low_event = _event(
        "evt_materiallow123",
        EventType.MATERIAL_LOW,
        {
            "material_ref": "mat_cement123",
            "quantity": 20,
            "unit": "bags",
            "supplier": "Delayed Logistics",
            "reason": "Required for tomorrow's plastering.",
        },
    )

    status, result_ref = _deliver(store, low_event)

    requests = store.repository(MaterialRequest).list(PROJECT_ID)
    approvals = store.repository(Approval).list(PROJECT_ID)
    low_run = store.repository(AgentRun).require(PROJECT_ID, run_id_for_event(low_event.event_id))
    assert status == "completed"
    assert result_ref == f"material_request:{requests[0].id}"
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("15")
    assert requests[0].supplier == "Delayed Logistics"
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert len(approvals) == 1
    assert low_run.workflow is WorkflowName.MATERIAL_SHORTAGE
    assert low_run.status is AgentRunStatus.WAITING_FOR_APPROVAL

    requested_event = _event(
        "evt_materialrequested123",
        EventType.MATERIAL_REQUESTED,
        {"request_id": requests[0].id},
        source=EventSource.SYSTEM,
    )
    requested_status, requested_ref = _deliver(store, requested_event)

    requested_run = store.repository(AgentRun).require(
        PROJECT_ID, run_id_for_event(requested_event.event_id)
    )
    assert requested_status == "completed"
    assert requested_ref == f"material_request:{requests[0].id}"
    assert requested_run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert any(
        activity.action == "material_request.workflow_observed"
        for activity in store.repository(ActivityEvent).list(PROJECT_ID)
    )


def test_blocked_and_overdue_events_persist_issues_and_task_impact() -> None:
    store = _store()
    store.repository(Task).create(
        Task(
            id="tsk_excavation123",
            project_id=PROJECT_ID,
            title="Excavation",
            status=TaskStatus.IN_PROGRESS,
            actual_start=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_foundation123",
            project_id=PROJECT_ID,
            title="Foundation",
            status=TaskStatus.PLANNED,
            dependency_ids=["tsk_excavation123"],
            created_at=NOW,
            updated_at=NOW,
        )
    )
    blocked_event = _event(
        "evt_taskblocked123",
        EventType.TASK_BLOCKED,
        {
            "description": "Excavator has failed.",
            "severity": "high",
            "task_refs": ["tsk_excavation123"],
        },
    )

    blocked_status, blocked_ref = _deliver(store, blocked_event)

    blocked_task = store.repository(Task).require(PROJECT_ID, "tsk_excavation123")
    blocked_issue = next(
        issue
        for issue in store.repository(Issue).list(PROJECT_ID)
        if blocked_event.event_id in issue.evidence_refs
    )
    assert blocked_status == "completed"
    assert blocked_ref == f"issue:{blocked_issue.id}"
    assert blocked_task.status is TaskStatus.BLOCKED
    assert blocked_issue.task_ids == ["tsk_excavation123", "tsk_foundation123"]
    assert (
        store.repository(AgentRun)
        .require(PROJECT_ID, run_id_for_event(blocked_event.event_id))
        .status
        is AgentRunStatus.COMPLETED
    )

    overdue_event = _event(
        "evt_taskoverdue123",
        EventType.TASK_OVERDUE,
        {"task_id": "tsk_foundation123", "expected_date": "2026-08-07"},
        source=EventSource.SYSTEM,
        actor_type=EventActorType.WORKLOAD,
        actor_id="wrk_scheduler123",
    )
    overdue_status, overdue_ref = _deliver(store, overdue_event)

    overdue_issue = next(
        issue
        for issue in store.repository(Issue).list(PROJECT_ID)
        if overdue_event.event_id in issue.evidence_refs
    )
    assert overdue_status == "completed"
    assert overdue_ref == f"issue:{overdue_issue.id}"
    assert overdue_issue.detected_by is IssueDetectedBy.OVERDUE_CHECK
    assert overdue_issue.task_ids == ["tsk_foundation123"]


def test_delivery_delay_updates_request_and_creates_downstream_risk() -> None:
    store = _store()
    store.repository(Project).create(
        Project(
            id=PROJECT_ID,
            name="Ridge Site",
            location="Accra",
            timezone="Africa/Accra",
            created_by=FOREMAN_ID,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_slab123",
            project_id=PROJECT_ID,
            title="Cast ground-floor slab",
            status=TaskStatus.PLANNED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id=PROJECT_ID,
            title="Start blockwork",
            status=TaskStatus.PLANNED,
            dependency_ids=["tsk_slab123"],
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement Bags",
            normalized_name="cement bags",
            unit="bags",
            available_quantity=Decimal("5"),
            updated_at=NOW,
        )
    )
    store.repository(Approval).create(
        Approval(
            id="app_cement123",
            project_id=PROJECT_ID,
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={
                "material_id": "mat_cement123",
                "affected_task_ids": ["tsk_slab123"],
            },
            reason="Cement required.",
            requested_by="system",
            status="approved",
            resolved_at=NOW,
            resolved_by=FOREMAN_ID,
            requested_at=NOW,
        )
    )
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id=PROJECT_ID,
            material_id="mat_cement123",
            quantity=Decimal("15"),
            unit="bags",
            reason="Cement required.",
            source_event_id="evt_materiallow123",
            status=MaterialRequestStatus.APPROVED,
            approval_id="app_cement123",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    event = _event(
        "evt_deliverydelay123",
        EventType.DELIVERY_DELAYED,
        {
            "request_id": "mrq_cement123",
            "new_date": "2026-08-13",
            "reason": "Supplier inventory is delayed.",
        },
        source=EventSource.WEB,
        actor_type=EventActorType.USER,
        actor_id=FOREMAN_ID,
    )

    gateway = FakeProjectNotificationGateway()
    status, result_ref = _deliver(store, event, notification_gateway=gateway)

    request = store.repository(MaterialRequest).require(PROJECT_ID, "mrq_cement123")
    issue = next(
        issue
        for issue in store.repository(Issue).list(PROJECT_ID)
        if event.event_id in issue.evidence_refs
    )
    follow_up = next(
        task
        for task in store.repository(Task).list(PROJECT_ID)
        if event.event_id in task.source_refs
    )
    notification = next(
        message
        for message in store.repository(OutboxMessage).list(PROJECT_ID)
        if message.message_type == "external_notification:delivery_delay"
    )
    assert status == "completed"
    assert result_ref == f"issue:{issue.id}"
    assert request.status is MaterialRequestStatus.DELAYED
    assert issue.detected_by is IssueDetectedBy.DELIVERY_EVENT
    assert issue.task_ids == ["tsk_blockwork123", "tsk_slab123"]
    assert follow_up.source is TaskSource.WORKFLOW
    assert notification.payload["follow_up_task_id"] == follow_up.id
    assert notification.provider == "google_chat"
    assert notification.provider_message_id is not None
    assert len(gateway.logical_sends) == 1
    assert (
        sum(event.event_id in task.source_refs for task in store.repository(Task).list(PROJECT_ID))
        == 1
    )
    assert (
        sum(
            message.message_type == "external_notification:delivery_delay"
            for message in store.repository(OutboxMessage).list(PROJECT_ID)
        )
        == 1
    )
    assert any(
        activity.action == "material_request.delayed"
        for activity in store.repository(ActivityEvent).list(PROJECT_ID)
    )


def test_daily_brief_event_upserts_source_linked_report_and_notification_once() -> None:
    store = _store(with_member=False)
    store.repository(Task).create(
        Task(
            id="tsk_completed123",
            project_id=PROJECT_ID,
            title="Ground-floor plumbing",
            status=TaskStatus.COMPLETED,
            completion_percent=Decimal("100"),
            actual_completion=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Issue).create(
        Issue(
            id="iss_blocker123",
            project_id=PROJECT_ID,
            type="delay_risk",
            severity="medium",
            description="Tile delivery is late.",
            evidence_refs=["evt_source123"],
            detected_by=IssueDetectedBy.DELIVERY_EVENT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    event = _event(
        "evt_dailybrief123",
        EventType.DAILY_BRIEF_REQUESTED,
        {"report_date": "2026-08-08", "timezone": "Africa/Accra"},
        source=EventSource.SCHEDULER,
        actor_type=EventActorType.WORKLOAD,
        actor_id="wrk_scheduler123",
        idempotency_key="a" * 256,
    )

    status, result_ref = _deliver(store, event)

    reports = store.repository(DailyReport).list(PROJECT_ID)
    outbox = store.repository(OutboxMessage).list(PROJECT_ID)
    activities = store.repository(ActivityEvent).list(PROJECT_ID)
    run = store.repository(AgentRun).require(PROJECT_ID, run_id_for_event(event.event_id))
    assert status == "completed"
    assert result_ref == f"daily_report:{reports[0].id}"
    assert len(reports) == 1
    assert reports[0].report_date == date(2026, 8, 8)
    assert [fact.summary for fact in reports[0].completed_work] == [
        "Ground-floor plumbing completed."
    ]
    assert [fact.summary for fact in reports[0].active_blockers] == ["Tile delivery is late."]
    assert (
        len([message for message in outbox if message.message_type == "notification:daily_brief"])
        == 1
    )
    assert len(outbox[0].deduplication_key) <= 256
    assert (
        len([activity for activity in activities if activity.action == "daily_brief.generated"])
        == 1
    )
    assert run.workflow is WorkflowName.DAILY_BRIEF
    assert run.status is AgentRunStatus.COMPLETED


@pytest.mark.backing_services
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for routed workflow persistence",
)
def test_routed_material_and_brief_state_survives_firestore_client_restart() -> None:
    firestore_project = f"oga-routed-{uuid4().hex}"
    project_id = f"prj_routed{uuid4().hex}"
    first_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    first_store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id=FOREMAN_ID,
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    first_store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=project_id,
            name="Cement Bags",
            normalized_name="cement bags",
            unit="bags",
            available_quantity=Decimal("5"),
            minimum_required_quantity=Decimal("20"),
            updated_at=NOW,
        )
    )
    low_event = _event(
        "evt_firestorematerial123",
        EventType.MATERIAL_LOW,
        {
            "material_ref": "mat_cement123",
            "quantity": 20,
            "unit": "bags",
            "reason": "Required for tomorrow's plastering.",
        },
        project_id=project_id,
    )

    process_event(low_event.model_dump_json().encode(), store=first_store)

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    requests = restarted_store.repository(MaterialRequest).list(project_id)
    assert len(requests) == 1
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert (
        restarted_store.repository(AgentRun)
        .require(project_id, run_id_for_event(low_event.event_id))
        .status
        is AgentRunStatus.WAITING_FOR_APPROVAL
    )

    brief_event = _event(
        "evt_firestorebrief123",
        EventType.DAILY_BRIEF_REQUESTED,
        {"report_date": "2026-08-08", "timezone": "Africa/Accra"},
        source=EventSource.SCHEDULER,
        actor_type=EventActorType.WORKLOAD,
        actor_id="wrk_scheduler123",
        project_id=project_id,
    )
    process_event(brief_event.model_dump_json().encode(), store=restarted_store)

    second_restart = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    reports = second_restart.repository(DailyReport).list(project_id)
    assert len(reports) == 1
    assert len(reports[0].material_risks) == 1
    activities = second_restart.repository(ActivityEvent).list(project_id)
    assert len(activities) == 4
    assert sum(activity.action == "material.risk_detected" for activity in activities) == 1
    assert len(second_restart.repository(OutboxMessage).list(project_id)) == 1
    assert (
        second_restart.repository(AgentRun)
        .require(project_id, run_id_for_event(brief_event.event_id))
        .status
        is AgentRunStatus.COMPLETED
    )


@pytest.mark.backing_services
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for approval continuation persistence",
)
def test_approved_material_continuation_completes_after_firestore_restart() -> None:
    firestore_project = f"oga-approval-{uuid4().hex}"
    project_id = f"prj_approval{uuid4().hex}"
    manager_id = "usr_manager123"
    first_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    first_store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id=FOREMAN_ID,
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    first_store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=project_id,
            name="Cement Bags",
            normalized_name="cement bags",
            unit="bags",
            available_quantity=Decimal("0"),
        )
    )
    shortage_event = _event(
        "evt_shortage123",
        EventType.MATERIAL_LOW,
        {
            "material_ref": "mat_cement123",
            "quantity": 150,
            "unit": "bags",
            "supplier": "Delayed Logistics",
            "reason": "Cement is required for tomorrow's plastering.",
        },
        project_id=project_id,
    )
    shortage = process_event(shortage_event.model_dump_json().encode(), store=first_store)
    assert shortage.status == "completed"
    approval = first_store.repository(Approval).list(project_id)[0]
    approved_at = datetime.now(UTC)
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=manager_id, subject="sub_manager123"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )
    ApprovalService(first_store).approve(
        access,
        ResolutionCommand(
            project_id=project_id,
            approval_id=approval.id,
            expected_version=0,
            occurred_at=approved_at,
        ),
        MutationContext(
            project_id=project_id,
            actor_type=ActorType.USER,
            actor_id=manager_id,
            source_event_id="evt_decision123",
            idempotency_key="approval:firestore:restart",
            occurred_at=approved_at,
        ),
    )
    approval_message = next(
        message
        for message in first_store.repository(OutboxMessage).list(project_id)
        if message.message_type == EventType.APPROVAL_GRANTED.value
    )
    event = ProjectEvent.model_validate(approval_message.payload)

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    first = process_event(event.model_dump_json().encode(), store=restarted_store)
    replay = process_event(event.model_dump_json().encode(), store=restarted_store)

    final_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project))
    assert first.status == "completed"
    assert replay.status == "duplicate"
    assert (
        final_store.repository(AgentRun)
        .require(project_id, run_id_for_event("evt_shortage123"))
        .status
        is AgentRunStatus.COMPLETED
    )
    request = final_store.repository(MaterialRequest).list(project_id)[0]
    assert (
        final_store.repository(MaterialRequest).require(project_id, request.id).status
        is MaterialRequestStatus.DELAYED
    )
    assert len(final_store.repository(Issue).list(project_id)) == 1
    assert len(final_store.repository(ProcessedEvent).list(project_id)) == 3
