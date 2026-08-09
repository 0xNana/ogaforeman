from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.events import (
    EVENT_SCHEMA_VERSION,
    EventActor,
    EventActorType,
    EventSource,
    EventType,
    ProjectEvent,
)


NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


def make_event(**updates: object) -> ProjectEvent:
    values: dict[str, object] = {
        "event_id": "evt_update001",
        "project_id": "prj_ridge",
        "event_type": EventType.SITE_UPDATE_RECEIVED,
        "source": EventSource.WEB,
        "occurred_at": NOW,
        "received_at": NOW,
        "actor": EventActor(type=EventActorType.USER, id="usr_foreman"),
        "idempotency_key": "site-update:sup_update001:v1",
        "correlation_id": "req_update001",
        "payload": {
            "site_update_id": "sup_update001",
            "text": "Blockwork is complete.",
            "transcript": None,
            "attachment_ids": [],
        },
        "metadata": {},
    }
    values.update(updates)
    return ProjectEvent(**values)


def test_registered_event_validates_and_fingerprint_is_deterministic() -> None:
    first = make_event()
    second = make_event(
        payload={
            "attachment_ids": [],
            "text": "Blockwork is complete.",
            "transcript": None,
            "site_update_id": "sup_update001",
        }
    )

    assert first.schema_version == EVENT_SCHEMA_VERSION == "1.0"
    assert first.event_type is EventType.SITE_UPDATE_RECEIVED
    assert first.fingerprint == second.fingerprint
    changed_actor = make_event(actor=EventActor(type=EventActorType.USER, id="usr_manager"))
    assert changed_actor.fingerprint != first.fingerprint


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (EventType.TASK_COMPLETED, {"task_id": "tsk_blockwork", "evidence_refs": []}),
        (
            EventType.TASK_BLOCKED,
            {"description": "Electrician absent", "severity": "high", "task_refs": []},
        ),
        (
            EventType.MATERIAL_LOW,
            {"material_ref": "mat_cement", "quantity": 12, "unit": "bags"},
        ),
        (EventType.MATERIAL_REQUESTED, {"request_id": "mrq_cement001"}),
        (
            EventType.DELIVERY_DELAYED,
            {"request_id": "mrq_cement001", "new_date": "2026-08-09", "reason": "rain"},
        ),
        (
            EventType.APPROVAL_GRANTED,
            {"approval_id": "apr_cement001", "resolver": "usr_manager", "notes": None},
        ),
        (
            EventType.APPROVAL_REJECTED,
            {"approval_id": "apr_cement001", "resolver": "usr_manager", "notes": "revise"},
        ),
        (
            EventType.TASK_OVERDUE,
            {"task_id": "tsk_blockwork", "expected_date": "2026-08-06"},
        ),
        (
            EventType.DAILY_BRIEF_REQUESTED,
            {"report_date": "2026-08-07", "timezone": "Africa/Accra"},
        ),
    ],
)
def test_all_registered_event_types_validate(
    event_type: EventType,
    payload: dict[str, object],
) -> None:
    event = make_event(event_type=event_type, payload=payload)

    assert event.event_type is event_type


def test_payload_must_match_registered_event_contract() -> None:
    with pytest.raises(ValidationError, match="site_update_id"):
        make_event(payload={"text": "missing update id"})

    with pytest.raises(ValidationError, match="event_type"):
        make_event(event_type="NOT_REGISTERED")

    with pytest.raises(ValidationError, match="idempotency_key"):
        make_event(idempotency_key="site-update/sup_update001")

    with pytest.raises(ValidationError, match="canonical ID"):
        make_event(payload={"site_update_id": "display name", "text": "update"})

    with pytest.raises(ValidationError, match="between 0 and 100"):
        make_event(
            event_type=EventType.TASK_COMPLETED,
            payload={"task_id": "tsk_blockwork", "evidence_refs": [], "completion_percent": 101},
        )

    with pytest.raises(ValidationError, match="negative"):
        make_event(
            event_type=EventType.MATERIAL_LOW,
            payload={"material_name": "Cement", "quantity": -1, "unit": "bags"},
        )


def test_event_payload_and_metadata_are_bounded_json() -> None:
    with pytest.raises(ValidationError, match="metadata exceeds"):
        make_event(metadata={"oversized": "x" * 65_536})

    nested: object = "value"
    for _ in range(18):
        nested = {"child": nested}
    with pytest.raises(ValidationError, match="nesting depth"):
        make_event(metadata={"nested": nested})

    with pytest.raises(ValidationError, match="non-JSON"):
        make_event(metadata={"unsupported": object()})


def test_event_rejects_naive_or_reversed_timestamps_and_is_frozen() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        make_event(occurred_at=datetime(2026, 8, 7, 10, 0))

    with pytest.raises(ValidationError, match="received_at"):
        make_event(received_at=datetime(2026, 8, 7, 9, 59, tzinfo=UTC))

    event = make_event()
    with pytest.raises(ValidationError):
        event.correlation_id = "req_other"
    with pytest.raises(TypeError, match="immutable"):
        event.payload["text"] = "changed"
    with pytest.raises(TypeError, match="immutable"):
        event.payload["attachment_ids"].append("att_other")
