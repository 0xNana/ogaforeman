"""Authenticated operator intake for real delivery-delay events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType, MaterialRequestStatus, OutboxStatus
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import OutboxMessage
from app.repositories.interfaces import RepositoryStore
from app.repositories.material_requests import MaterialRequestRepository
from app.services.activity import ActivityService
from app.services.outbox import OutboxService
from app.services.site_update_intake import EventPublisher


class DeliveryDelayPublishError(RuntimeError):
    code = "EVENT_TRANSPORT_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class DeliveryDelayIntakeResult:
    event_id: str
    message_id: str


class DeliveryDelayIntakeService:
    def __init__(self, store: RepositoryStore, publisher: EventPublisher) -> None:
        self._store = store
        self._publisher = publisher
        self._activities = ActivityService(store)
        self._outbox = OutboxService(store)

    def submit(
        self,
        access: ProjectAccessContext,
        *,
        material_request_id: str,
        revised_delivery_date: date,
        reason: str,
        idempotency_key: str,
        occurred_at: datetime | None = None,
    ) -> DeliveryDelayIntakeResult:
        ensure_project_scope(access, access.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        request = MaterialRequestRepository.for_session(self._store, access).require(
            access.project_id, material_request_id
        )
        if request.status not in {
            MaterialRequestStatus.APPROVED,
            MaterialRequestStatus.SUBMITTED,
            MaterialRequestStatus.CONFIRMED,
            MaterialRequestStatus.DELAYED,
        }:
            raise ValueError("material request is not eligible for a delivery-delay report")
        received_at = datetime.now(UTC)
        reported_at = occurred_at or received_at
        if reported_at > received_at:
            raise ValueError("occurred_at cannot be in the future")
        digest = sha256(
            f"{access.project_id}\x00{access.actor.user_id}\x00{idempotency_key}".encode("utf-8")
        ).hexdigest()[:32]
        event_id = f"evt_{digest}"
        outbox_id = f"obx_{digest}"
        event = ProjectEvent(
            event_id=event_id,
            project_id=access.project_id,
            event_type=EventType.DELIVERY_DELAYED,
            source=EventSource.WEB,
            occurred_at=reported_at,
            received_at=received_at,
            actor=EventActor(type=EventActorType.USER, id=access.actor.user_id),
            idempotency_key=idempotency_key,
            correlation_id=event_id,
            payload={
                "request_id": request.id,
                "new_date": revised_delivery_date.isoformat(),
                "reason": reason,
            },
        )
        outbox = OutboxMessage(
            id=outbox_id,
            project_id=access.project_id,
            message_type=event.event_type.value,
            deduplication_key=event.idempotency_key,
            payload=event.model_dump(mode="json"),
        )
        input_digest = sha256(
            json.dumps(
                {
                    "request_id": request.id,
                    "new_date": revised_delivery_date.isoformat(),
                    "reason": reason,
                    "occurred_at": reported_at.isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            source_event_id=event_id,
            idempotency_key=idempotency_key,
            occurred_at=received_at,
        )
        mutation = self._activities.mutate(
            context,
            ActivitySpec(
                action="delivery_delay.received",
                entity_type="outbox_message",
                entity_id=outbox.id,
                summary="Received an authenticated delivery-delay report.",
                metadata={
                    "material_request_id": request.id,
                    "input_digest": input_digest,
                },
            ),
            lambda session: session.repository(OutboxMessage).create(outbox),
            replay=lambda session, _activity: session.repository(OutboxMessage).require(
                access.project_id, outbox.id
            ),
        )
        if mutation.value is None:
            raise RuntimeError("delivery-delay replay did not resolve persisted event")

        def publish(message: OutboxMessage) -> None:
            self._publisher.publish(
                None,
                ProjectEvent.model_validate(message.payload).model_dump_json().encode("utf-8"),
                attributes={
                    "event_type": event.event_type.value,
                    "project_id": event.project_id,
                    "schema_version": event.schema_version,
                },
            )

        publish_context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=event_id,
            idempotency_key=f"delivery-delay-publish:{digest}",
            occurred_at=received_at,
        )
        processed = self._outbox.process(
            access.project_id,
            outbox.id,
            publish,
            audit_context=publish_context,
        )
        if processed.status is not OutboxStatus.COMPLETED:
            raise DeliveryDelayPublishError(
                "delivery delay is persisted but event publication failed"
            )
        return DeliveryDelayIntakeResult(event_id=event.event_id, message_id=processed.id)


__all__ = [
    "DeliveryDelayIntakeResult",
    "DeliveryDelayIntakeService",
    "DeliveryDelayPublishError",
]
