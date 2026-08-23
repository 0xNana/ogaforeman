from datetime import UTC, datetime

import pytest

from app.agents.identifiers import AdkWorkflowId
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.services.event_router import route_project_event


def create_test_event(event_type: EventType, payload: dict) -> ProjectEvent:
    return ProjectEvent(
        event_id="evt_test123",
        project_id="prj_test456",
        event_type=event_type,
        source=EventSource.WEB,
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        actor=EventActor(type=EventActorType.USER, id="usr_test789"),
        idempotency_key="idemp_key123",
        correlation_id="cor_id123",
        payload=payload,
    )


def test_site_update_projection_names_the_real_workflow() -> None:
    event = create_test_event(
        EventType.SITE_UPDATE_RECEIVED,
        {"site_update_id": "sup_123", "text": "test update"},
    )

    assert route_project_event(event) == AdkWorkflowId.DAILY_SITE_UPDATE


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (EventType.MATERIAL_LOW, {"material_name": "cement", "quantity": 10, "unit": "bags"}),
        (
            EventType.TASK_BLOCKED,
            {"description": "No power", "severity": "high", "task_refs": []},
        ),
        (
            EventType.DAILY_BRIEF_REQUESTED,
            {"report_date": "2026-08-07", "timezone": "Africa/Accra"},
        ),
    ],
)
def test_remaining_typed_events_project_through_the_generic_workflow(
    event_type: EventType,
    payload: dict,
) -> None:
    assert route_project_event(create_test_event(event_type, payload)) == (
        AdkWorkflowId.PROJECT_EVENT
    )


def test_delivery_delay_projection_names_its_dedicated_workflow() -> None:
    event = create_test_event(
        EventType.DELIVERY_DELAYED,
        {
            "request_id": "mrq_test123",
            "new_date": "2026-08-30",
            "reason": "Vehicle breakdown",
        },
    )

    assert route_project_event(event) == AdkWorkflowId.DELIVERY_DELAY
