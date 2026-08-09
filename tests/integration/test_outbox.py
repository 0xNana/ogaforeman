import pytest
from unittest.mock import Mock

from app.domain.models import OutboxStatus
from app.repositories.memory import InMemoryRepositoryStore
from app.services.outbox import OutboxService


@pytest.fixture
def store():
    return InMemoryRepositoryStore()


@pytest.fixture
def service(store):
    return OutboxService(store)


def test_outbox_success(service):
    project_id = "prj_123"
    message_type = "notification"
    payload = {"foo": "bar"}
    deduplication_key = "test1"

    msg = service.queue(project_id, message_type, payload, deduplication_key)
    assert msg.status == OutboxStatus.PENDING
    assert msg.message_type == message_type

    handler = Mock()
    processed_msg = service.process(project_id, msg.id, handler)
    assert processed_msg.status == OutboxStatus.COMPLETED
    assert processed_msg.processed_at is not None
    handler.assert_called_once()


def test_outbox_crash_before_ack(service):
    project_id = "prj_123"
    msg = service.queue(project_id, "test", {}, "test2")

    handler = Mock(side_effect=Exception("Crash"))

    processed_msg = service.process(project_id, msg.id, handler)
    assert processed_msg.status == OutboxStatus.FAILED
    assert processed_msg.attempts == 1
    assert processed_msg.last_error is not None
    assert "Crash" in processed_msg.last_error
    handler.assert_called_once()

    # Retry
    success_handler = Mock()
    retried_msg = service.process(project_id, msg.id, success_handler)
    assert retried_msg.status == OutboxStatus.COMPLETED
    assert retried_msg.attempts == 2
    success_handler.assert_called_once()


def test_outbox_duplicate_delivery(service):
    project_id = "prj_123"
    dedup_key = "test3"

    msg1 = service.queue(project_id, "test", {}, dedup_key)
    msg2 = service.queue(project_id, "test", {}, dedup_key)

    assert msg1.id == msg2.id

    handler = Mock()
    processed_msg1 = service.process(project_id, msg1.id, handler)
    assert processed_msg1.status == OutboxStatus.COMPLETED
    assert handler.call_count == 1

    # Process again
    processed_msg2 = service.process(project_id, msg1.id, handler)
    assert processed_msg2.status == OutboxStatus.COMPLETED
    assert handler.call_count == 1  # Not called again
