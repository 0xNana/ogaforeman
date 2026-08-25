from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.enums import (
    IssueDetectedBy,
    IssueType,
    MaterialRequestStatus,
    OutboxStatus,
    Severity,
    TaskSource,
    TaskStatus,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    Project,
    Task,
)
from app.infrastructure.notification_gateway import (
    PermanentNotificationGatewayError,
    TransientNotificationGatewayError,
)
from app.infrastructure.disabled_notification import DisabledNotificationProvider
from app.infrastructure.logging_notification import LoggingNotificationProvider
from app.repositories.memory import InMemoryRepositoryStore
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.delivery_notifications import (
    DeliveryNotificationError,
    NotificationService,
)
from app.services.routed_events import DeliveryDelayAssessment, DeliveryDelayContext
from tests.fakes import FakeProjectNotificationGateway


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PROJECT_ID = "prj_notify123"
RUN_ID = "run_notify123"


def _scenario():
    project = Project(
        id=PROJECT_ID,
        name="Ridge Site",
        location="Accra",
        timezone="Africa/Accra",
        created_by="usr_manager123",
        created_at=NOW,
        updated_at=NOW,
    )
    material = Material(
        id="mat_cement123",
        project_id=PROJECT_ID,
        name="Cement Bags",
        normalized_name="cement bags",
        unit="bags",
        available_quantity=Decimal("10"),
        updated_at=NOW,
    )
    request = MaterialRequest(
        id="mrq_cement123",
        project_id=PROJECT_ID,
        material_id=material.id,
        quantity=Decimal("90"),
        unit="bags",
        reason="Plastering requirement.",
        source_event_id="evt_shortage123",
        status=MaterialRequestStatus.DELAYED,
        approval_id="app_cement123",
        created_at=NOW,
        updated_at=NOW,
    )
    slab = Task(
        id="tsk_slab123",
        project_id=PROJECT_ID,
        title="Cast slab",
        status=TaskStatus.PLANNED,
        created_at=NOW,
        updated_at=NOW,
    )
    blockwork = Task(
        id="tsk_blockwork123",
        project_id=PROJECT_ID,
        title="Start blockwork",
        status=TaskStatus.PLANNED,
        dependency_ids=[slab.id],
        created_at=NOW,
        updated_at=NOW,
    )
    event = ProjectEvent(
        event_id="evt_delivery123",
        project_id=PROJECT_ID,
        event_type=EventType.DELIVERY_DELAYED,
        source=EventSource.WEB,
        occurred_at=NOW,
        received_at=NOW,
        actor=EventActor(type=EventActorType.USER, id="usr_manager123"),
        idempotency_key="delivery-delay:real:123",
        correlation_id="cor_delivery123",
        payload={
            "request_id": request.id,
            "new_date": "2026-08-30",
            "reason": "Supplier confirmed a vehicle breakdown.",
        },
    )
    issue = Issue(
        id="iss_delay123",
        project_id=PROJECT_ID,
        type=IssueType.DELAY_RISK,
        severity=Severity.HIGH,
        description="Delivery delay affects slab and blockwork.",
        evidence_refs=[event.event_id],
        task_ids=[slab.id, blockwork.id],
        detected_by=IssueDetectedBy.DELIVERY_EVENT,
        created_at=NOW,
        updated_at=NOW,
    )
    follow_up = Task(
        id="tsk_followup123",
        project_id=PROJECT_ID,
        title="Follow up delayed cement delivery",
        status=TaskStatus.PROPOSED,
        source=TaskSource.WORKFLOW,
        source_refs=[event.event_id],
        created_at=NOW,
        updated_at=NOW,
    )
    context = DeliveryDelayContext(
        project=project,
        request=request,
        material=material,
        tasks=(slab, blockwork),
        directly_affected_task_ids=(slab.id,),
    )
    assessment = DeliveryDelayAssessment(
        affected_task_ids=(blockwork.id, slab.id),
        severity=Severity.HIGH,
    )
    return event, context, assessment, issue, follow_up


def test_delivery_notification_replay_sends_one_logical_google_chat_message() -> None:
    store = InMemoryRepositoryStore()
    gateway = FakeProjectNotificationGateway()
    service = NotificationService(store, gateway, base_backoff_seconds=0)
    scenario = _scenario()

    first = service.deliver(scenario[0], RUN_ID, *scenario[1:])
    replay = service.deliver(scenario[0], RUN_ID, *scenario[1:])

    assert first.status is OutboxStatus.COMPLETED
    assert replay.id == first.id
    assert len(gateway.logical_sends) == 1
    payload = gateway.attempts[0][0]
    assert payload.project_name == "Ridge Site"
    assert payload.material_name == "Cement Bags"
    assert payload.event_id == "evt_delivery123"
    assert [task.title for task in payload.affected_tasks] == ["Start blockwork", "Cast slab"]
    assert payload.follow_up_task_id == "tsk_followup123"
    actions = [activity.action for activity in store.repository(ActivityEvent).list(PROJECT_ID)]
    assert actions.count("external_notification.attempted") == 1
    assert actions.count("external_notification.sent") == 1


def test_transient_provider_failure_retries_with_same_logical_key() -> None:
    store = InMemoryRepositoryStore()
    gateway = FakeProjectNotificationGateway([TransientNotificationGatewayError("temporary"), None])
    service = NotificationService(store, gateway, base_backoff_seconds=0)
    scenario = _scenario()

    message = service.deliver(scenario[0], RUN_ID, *scenario[1:])

    assert message.status is OutboxStatus.COMPLETED
    assert message.attempts == 2
    assert gateway.attempts[0][1] == gateway.attempts[1][1]
    assert len(gateway.logical_sends) == 1


def test_logging_provider_is_explicitly_development_only() -> None:
    store = InMemoryRepositoryStore()
    service = NotificationService(
        store,
        LoggingNotificationProvider(),
        base_backoff_seconds=0,
    )
    scenario = _scenario()

    message = service.deliver(scenario[0], RUN_ID, *scenario[1:])

    assert message.status is OutboxStatus.COMPLETED
    assert message.provider == "logging"
    assert message.message_type == "development_notification:delivery_delay"
    actions = [activity.action for activity in store.repository(ActivityEvent).list(PROJECT_ID)]
    assert "development_notification.recorded" in actions
    assert "external_notification.sent" not in actions


def test_disabled_provider_persists_one_skipped_external_outcome_without_attempting() -> None:
    store = InMemoryRepositoryStore()
    service = NotificationService(
        store,
        DisabledNotificationProvider(),
        base_backoff_seconds=0,
        clock=lambda: NOW,
    )
    scenario = _scenario()

    first = service.deliver(scenario[0], RUN_ID, *scenario[1:])
    replay = service.deliver(scenario[0], RUN_ID, *scenario[1:])

    assert first.status is OutboxStatus.SKIPPED
    assert replay == first
    assert first.provider == "disabled"
    assert first.message_type == "external_notification:delivery_delay"
    assert first.attempts == 0
    assert first.provider_message_id is None
    assert first.processed_at == NOW
    actions = [activity.action for activity in store.repository(ActivityEvent).list(PROJECT_ID)]
    assert actions.count("external_notification.skipped") == 1
    assert "external_notification.attempted" not in actions
    assert "external_notification.sent" not in actions


@pytest.mark.backing_services
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for notification persistence",
)
def test_disabled_provider_persists_skipped_outcome_in_firestore_transaction() -> None:
    store = FirestoreRepositoryStore(firestore.Client(project=f"oga-notify-{uuid4().hex}"))
    service = NotificationService(
        store,
        DisabledNotificationProvider(),
        base_backoff_seconds=0,
        clock=lambda: NOW,
    )
    scenario = _scenario()

    message = service.deliver(scenario[0], RUN_ID, *scenario[1:])

    assert message.status is OutboxStatus.SKIPPED
    actions = [activity.action for activity in store.repository(ActivityEvent).list(PROJECT_ID)]
    assert actions.count("external_notification.skipped") == 1


def test_permanent_provider_failure_is_terminal_and_visible() -> None:
    store = InMemoryRepositoryStore()
    gateway = FakeProjectNotificationGateway(
        [PermanentNotificationGatewayError("invalid destination")]
    )
    service = NotificationService(store, gateway, base_backoff_seconds=0)
    event, context, assessment, issue, follow_up = _scenario()
    store.repository(MaterialRequest).create(context.request)
    store.repository(Issue).create(issue)
    store.repository(Task).create(follow_up)

    with pytest.raises(DeliveryNotificationError):
        service.deliver(event, RUN_ID, context, assessment, issue, follow_up)

    message = store.repository(OutboxMessage).list(PROJECT_ID)[0]
    assert message.status is OutboxStatus.DEAD_LETTERED
    assert message.failure_kind == "permanent"
    assert message.provider_message_id is None
    assert store.repository(MaterialRequest).require(PROJECT_ID, context.request.id).status is (
        MaterialRequestStatus.DELAYED
    )
    assert store.repository(Issue).require(PROJECT_ID, issue.id) == issue
    assert store.repository(Task).require(PROJECT_ID, follow_up.id) == follow_up
    assert any(
        activity.action == "external_notification.failed"
        for activity in store.repository(ActivityEvent).list(PROJECT_ID)
    )
    assert any(
        activity.action == "external_notification.attempted"
        for activity in store.repository(ActivityEvent).list(PROJECT_ID)
    )


def test_expired_claim_reuses_provider_idempotency_after_process_loss() -> None:
    store = InMemoryRepositoryStore()
    gateway = FakeProjectNotificationGateway()
    current = [NOW]
    service = NotificationService(
        store,
        gateway,
        base_backoff_seconds=0,
        claim_lease_seconds=5,
        clock=lambda: current[0],
    )
    event, context, assessment, issue, follow_up = _scenario()
    payload = service._payload(event, context, assessment, issue, follow_up)
    queued = service._queue(event, RUN_ID, payload)
    claimed = service._claim(event, RUN_ID, queued.id).message
    gateway.send_delivery_delay(payload, idempotency_key=claimed.deduplication_key)

    current[0] = NOW + timedelta(seconds=6)
    completed = service.deliver(event, RUN_ID, context, assessment, issue, follow_up)

    assert completed.status is OutboxStatus.COMPLETED
    assert completed.attempts == 2
    assert len(gateway.logical_sends) == 1


def test_notification_telemetry_names_outbox_provider_and_delivery_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryRepositoryStore()
    gateway = FakeProjectNotificationGateway()
    service = NotificationService(store, gateway, base_backoff_seconds=0)
    scenario = _scenario()

    with caplog.at_level(logging.INFO, logger="ogaforeman.notifications.delivery"):
        message = service.deliver(scenario[0], RUN_ID, *scenario[1:])

    sent = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "delivery_notification_sent"
    )
    fields = sent.oga_fields
    assert fields["outbox_item_id"] == message.id
    assert fields["provider"] == "google_chat"
    assert fields["delivery_status"] == "completed"
    assert "token" not in str(fields).lower()
