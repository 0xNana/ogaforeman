from datetime import UTC, datetime


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


def test_coordinator_routing_site_update() -> None:
    event = create_test_event(
        EventType.SITE_UPDATE_RECEIVED,
        {"site_update_id": "sup_123", "text": "test update"},
    )
    decision = route_project_event(event)
    assert decision == "site_report"


def test_coordinator_routing_materials() -> None:
    event = create_test_event(
        EventType.MATERIAL_LOW,
        {"material_name": "cement", "quantity": 10, "unit": "bags"},
    )
    decision = route_project_event(event)
    assert decision == "materials"


def test_coordinator_routing_planner() -> None:
    event = create_test_event(
        EventType.TASK_BLOCKED,
        {"description": "No power", "severity": "high", "task_refs": []},
    )
    decision = route_project_event(event)
    assert decision == "planner"


def test_coordinator_routing_daily_brief() -> None:
    event = create_test_event(
        EventType.DAILY_BRIEF_REQUESTED,
        {"report_date": "2026-08-07", "timezone": "Africa/Accra"},
    )
    decision = route_project_event(event)
    assert decision == "communicator"
