import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.enums import ApprovalActionType, ApprovalStatus, MaterialRequestStatus
from app.domain.events import EventType
from app.domain.models import Approval, MaterialRequest, OutboxMessage, OutboxStatus
from app.repositories.memory import InMemoryRepositoryStore
from app.services.outbox import OutboxService
from app.services.external_actions import ExternalActionService


@pytest.fixture
def store():
    return InMemoryRepositoryStore()


@pytest.fixture
def setup_state(store):
    def _setup(session):
        approvals = session.repository(Approval)
        approvals.create(
            Approval(
                id="app_123",
                project_id="prj_123",
                action_type=ApprovalActionType.PURCHASE,
                proposed_action={"item": "Paint"},
                reason="Need paint",
                requested_by="system",
                requested_at=datetime.now(UTC) - timedelta(minutes=1),
                status=ApprovalStatus.APPROVED,
                resolved_by="usr_123",
                resolved_at=datetime.now(UTC),
            )
        )

        requests = session.repository(MaterialRequest)
        requests.create(
            MaterialRequest(
                id="req_123",
                project_id="prj_123",
                material_id="mat_123",
                quantity=Decimal("150"),  # Trigger delay
                unit="litres",
                reason="Need paint",
                source_event_id="evt_trigger",
                status=MaterialRequestStatus.APPROVED,
                approval_id="app_123",
            )
        )

    store.run_transaction(_setup)


def test_external_actions_outbox_claim_and_delayed_delivery(store, setup_state):
    outbox = OutboxService(store)
    service = ExternalActionService(store)

    # Queue an APPROVAL_GRANTED message
    msg = outbox.queue(
        project_id="prj_123",
        message_type=EventType.APPROVAL_GRANTED.value,
        payload={"approval_id": "app_123", "resolver": "usr_123"},
        deduplication_key="test_approval",
    )

    # Process it
    service.process_outbox_message("prj_123", msg.id)

    # The outbox message should be completed
    messages = store.run_transaction(lambda s: list(s.repository(OutboxMessage).list("prj_123")))
    original_msg = next(m for m in messages if m.id == msg.id)
    assert original_msg.status == OutboxStatus.COMPLETED
    assert (
        store.repository(MaterialRequest).require("prj_123", "req_123").status
        is MaterialRequestStatus.SUBMITTED
    )

    # Because quantity > 100, it should have queued a DELIVERY_DELAYED event
    delay_msgs = [m for m in messages if m.message_type == EventType.DELIVERY_DELAYED.value]
    assert len(delay_msgs) == 1
    assert delay_msgs[0].status == OutboxStatus.PENDING
    assert delay_msgs[0].payload["event_type"] == EventType.DELIVERY_DELAYED.value
    assert delay_msgs[0].payload["payload"]["request_id"] == "req_123"


def test_external_actions_replay_safe(store, setup_state):
    outbox = OutboxService(store)
    service = ExternalActionService(store)

    # Queue an APPROVAL_GRANTED message
    msg = outbox.queue(
        project_id="prj_123",
        message_type=EventType.APPROVAL_GRANTED.value,
        payload={"approval_id": "app_123", "resolver": "usr_123"},
        deduplication_key="test_approval",
    )

    # Process it twice (simulating replay of processing)
    service.process_outbox_message("prj_123", msg.id)
    service.process_outbox_message("prj_123", msg.id)

    # The outbox message should be completed
    messages = store.run_transaction(lambda s: list(s.repository(OutboxMessage).list("prj_123")))
    delay_msgs = [m for m in messages if m.message_type == EventType.DELIVERY_DELAYED.value]

    # Still only 1 delay message because the OutboxService idempotency/replay prevents double processing
    # of the original message since it becomes COMPLETED after the first run.
    assert len(delay_msgs) == 1
