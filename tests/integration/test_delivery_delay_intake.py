from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.v1.delivery_delays import router as delivery_delay_router
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectForbiddenError,
    ProjectPermission,
)
from app.domain.enums import MaterialRequestStatus, MemberRole, OutboxStatus
from app.domain.events import (
    EventActor,
    EventActorType,
    EventSource,
    EventType,
    ProjectEvent,
)
from app.domain.models import ActivityEvent, MaterialRequest, OutboxMessage
from app.repositories.memory import InMemoryRepositoryStore
from app.services.delivery_delay_intake import DeliveryDelayIntakeService
from app.services.routed_events import TypedEventService


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[bytes] = []

    def publish(self, _topic, data: bytes, *, attributes=None) -> str:
        self.messages.append(data)
        return "msg_delivery123"


def test_authenticated_delivery_delay_intake_persists_one_normalized_event() -> None:
    store = InMemoryRepositoryStore()
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id="prj_ridge123",
            material_id="mat_cement123",
            quantity=Decimal("90"),
            unit="bags",
            reason="Plastering requirement.",
            source_event_id="evt_shortage123",
            status=MaterialRequestStatus.APPROVED,
            approval_id="app_cement123",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="firebase-manager"),
        project_id="prj_ridge123",
        role=MemberRole.MANAGER,
    )
    publisher = FakePublisher()
    service = DeliveryDelayIntakeService(store, publisher)

    first = service.submit(
        access,
        material_request_id="mrq_cement123",
        revised_delivery_date=date(2026, 8, 30),
        reason="Supplier confirmed a vehicle breakdown.",
        occurred_at=NOW,
        idempotency_key="operator-delay-123",
    )
    replay = service.submit(
        access,
        material_request_id="mrq_cement123",
        revised_delivery_date=date(2026, 8, 30),
        reason="Supplier confirmed a vehicle breakdown.",
        occurred_at=NOW,
        idempotency_key="operator-delay-123",
    )

    assert replay.event_id == first.event_id
    assert len(publisher.messages) == 1
    event = ProjectEvent.model_validate_json(publisher.messages[0])
    assert event.event_type is EventType.DELIVERY_DELAYED
    assert event.payload["request_id"] == "mrq_cement123"
    persisted = store.repository(OutboxMessage).require("prj_ridge123", first.message_id)
    assert persisted.status is OutboxStatus.COMPLETED
    assert (
        sum(
            activity.action == "delivery_delay.received"
            for activity in store.repository(ActivityEvent).list("prj_ridge123")
        )
        == 1
    )


@pytest.mark.asyncio
async def test_delivery_delay_http_boundary_requires_authenticated_project_access() -> None:
    store = InMemoryRepositoryStore()
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id="prj_ridge123",
            material_id="mat_cement123",
            quantity=Decimal("90"),
            unit="bags",
            reason="Plastering requirement.",
            source_event_id="evt_shortage123",
            status=MaterialRequestStatus.APPROVED,
            approval_id="app_cement123",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    publisher = FakePublisher()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(
        delivery_delay_router,
        prefix="/api/v1/projects/{project_id}/delivery-delays",
    )
    app.state.delivery_delay_intake = DeliveryDelayIntakeService(store, publisher)
    request_body = {
        "material_request_id": "mrq_cement123",
        "revised_delivery_date": "2026-08-30",
        "reason": "Supplier confirmed a vehicle breakdown.",
        "occurred_at": NOW.isoformat(),
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthenticated = await client.post(
            "/api/v1/projects/prj_ridge123/delivery-delays",
            headers={"Idempotency-Key": "operator-delay-http-123"},
            json=request_body,
        )
        assert unauthenticated.status_code == 401

        def provide_access(
            _request: object,
            project_id: str,
            permission: ProjectPermission,
        ) -> ProjectAccessContext:
            assert project_id == "prj_ridge123"
            assert permission is ProjectPermission.OPERATE
            return ProjectAccessContext(
                actor=AuthenticatedUser(
                    user_id="usr_manager123",
                    subject="firebase-manager",
                ),
                project_id=project_id,
                role=MemberRole.MANAGER,
            )

        app.state.project_access_provider = provide_access
        accepted = await client.post(
            "/api/v1/projects/prj_ridge123/delivery-delays",
            headers={"Idempotency-Key": "operator-delay-http-123"},
            json=request_body,
        )

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"
    assert len(publisher.messages) == 1
    event = ProjectEvent.model_validate_json(publisher.messages[0])
    assert event.event_type is EventType.DELIVERY_DELAYED
    assert event.actor.id == "usr_manager123"


def test_delivery_delay_worker_rejects_direct_integration_event_injection() -> None:
    event = ProjectEvent(
        event_id="evt_directintegration123",
        project_id="prj_ridge123",
        event_type=EventType.DELIVERY_DELAYED,
        source=EventSource.INTEGRATION,
        occurred_at=NOW,
        received_at=NOW,
        actor=EventActor(
            type=EventActorType.INTEGRATION,
            id="int_untrusted123",
        ),
        idempotency_key="direct-integration-delay-123",
        correlation_id="cor_directintegration123",
        payload={
            "request_id": "mrq_cement123",
            "new_date": "2026-08-30",
            "reason": "Untrusted direct event.",
        },
    )

    with pytest.raises(ProjectForbiddenError, match="authenticated operator intake"):
        TypedEventService(InMemoryRepositoryStore()).start_delivery_delay(event)
