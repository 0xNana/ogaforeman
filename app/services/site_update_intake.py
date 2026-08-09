"""Authenticated, durable intake for site updates."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    AttachmentUploadStatus,
    SiteUpdateInputType,
    WorkflowName,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Attachment,
    OutboxMessage,
    OutboxStatus,
    SiteUpdate,
)
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.services.activity import ActivityService
from app.services.outbox import OutboxService
from app.workflows.runtime import run_id_for_event


class EventPublisher(Protocol):
    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        """Publish one persisted project event and return its transport ID."""


class SiteUpdatePublishError(RuntimeError):
    code = "EVENT_TRANSPORT_UNAVAILABLE"


class SiteUpdateAttachmentError(ValueError):
    code = "ATTACHMENT_INVALID"


@dataclass(frozen=True, slots=True)
class SiteUpdateIntakeResult:
    site_update_id: str
    event_id: str
    agent_run_id: str
    message_id: str


class SiteUpdateIntakeService:
    def __init__(self, store: RepositoryStore, publisher: EventPublisher) -> None:
        self._store = store
        self._publisher = publisher
        self._activities = ActivityService(store)
        self._outbox = OutboxService(store)

    def submit(
        self,
        access: ProjectAccessContext,
        *,
        idempotency_key: str,
        raw_text: str | None = None,
        transcript: str | None = None,
        attachment_ids: Sequence[str] = (),
        input_type: SiteUpdateInputType | None = None,
        client_event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> SiteUpdateIntakeResult:
        ensure_project_scope(access, access.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        received_at = datetime.now(UTC)
        submitted_at = occurred_at or received_at
        if submitted_at > received_at:
            raise ValueError("occurred_at cannot be in the future")

        digest = sha256(
            f"{access.project_id}\x00{access.actor.user_id}\x00{idempotency_key}".encode("utf-8")
        ).hexdigest()[:32]
        site_update_id = f"sup_{digest}"
        event_id = f"evt_{digest}"
        run_id = run_id_for_event(event_id)
        outbox_id = f"obx_{digest}"
        resolved_input_type = input_type or _infer_input_type(
            raw_text,
            transcript,
            attachment_ids,
        )
        update = SiteUpdate(
            id=site_update_id,
            project_id=access.project_id,
            submitted_by=access.actor.user_id,
            input_type=resolved_input_type,
            raw_text=raw_text,
            transcript=transcript,
            attachment_ids=list(attachment_ids),
            client_event_id=client_event_id or idempotency_key,
            submitted_at=submitted_at,
            created_at=received_at,
            updated_at=received_at,
        )
        event = ProjectEvent(
            event_id=event_id,
            project_id=access.project_id,
            event_type=EventType.SITE_UPDATE_RECEIVED,
            source=EventSource.WEB,
            occurred_at=submitted_at,
            received_at=received_at,
            actor=EventActor(type=EventActorType.USER, id=access.actor.user_id),
            idempotency_key=idempotency_key,
            correlation_id=event_id,
            payload={
                "site_update_id": site_update_id,
                "text": raw_text,
                "transcript": transcript,
                "attachment_ids": list(attachment_ids),
            },
        )
        run = AgentRun(
            id=run_id,
            project_id=access.project_id,
            trigger_event_id=event_id,
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.QUEUED,
            trace_id=event_id,
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
                    "input_type": resolved_input_type.value,
                    "raw_text": raw_text,
                    "transcript": transcript,
                    "attachment_ids": list(attachment_ids),
                    "client_event_id": client_event_id,
                    "occurred_at": occurred_at.isoformat() if occurred_at else None,
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
            agent_run_id=run_id,
            idempotency_key=idempotency_key,
            occurred_at=received_at,
        )
        spec = ActivitySpec(
            action="site_update.received",
            entity_type="site_update",
            entity_id=site_update_id,
            summary="Received a site update.",
            metadata={"input_digest": input_digest},
        )

        mutation = self._activities.mutate(
            context,
            spec,
            lambda session: _persist_intake(session, update, run, outbox, context),
            replay=lambda session, activity: session.repository(SiteUpdate).require(
                access.project_id,
                activity.entity_id,
            ),
        )
        if mutation.value is None:
            raise RuntimeError("site-update replay did not resolve persisted state")

        def publish(message: OutboxMessage) -> None:
            self._publisher.publish(
                None,
                ProjectEvent.model_validate(message.payload).model_dump_json().encode("utf-8"),
                attributes={
                    "event_type": event.event_type.value,
                    "project_id": access.project_id,
                    "schema_version": event.schema_version,
                },
            )

        processed = self._outbox.process(access.project_id, outbox_id, publish)
        if processed.status is not OutboxStatus.COMPLETED:
            raise SiteUpdatePublishError("site update is persisted but event publication failed")

        return SiteUpdateIntakeResult(
            site_update_id=site_update_id,
            event_id=event_id,
            agent_run_id=run_id,
            message_id=processed.id,
        )


def _persist_intake(
    session: RepositorySession,
    update: SiteUpdate,
    run: AgentRun,
    outbox: OutboxMessage,
    context: MutationContext,
) -> SiteUpdate:
    attachments = session.repository(Attachment)
    activities = session.repository(ActivityEvent)
    attachments_to_link: list[tuple[Attachment, int]] = []
    for attachment_id in update.attachment_ids:
        attachment = attachments.get(update.project_id, attachment_id)
        if attachment is None:
            raise SiteUpdateAttachmentError(
                "site update attachment was not found in the authorized project"
            )
        if attachment.upload_status is not AttachmentUploadStatus.VERIFIED:
            raise SiteUpdateAttachmentError("site update attachment must be verified")
        if attachment.site_update_id not in {None, update.id}:
            raise SiteUpdateAttachmentError("site update attachment is already linked")
        if attachment.site_update_id == update.id:
            continue
        version = attachments.version_of(update.project_id, attachment.id)
        if version is None:
            raise RuntimeError("site update attachment disappeared")
        attachments_to_link.append((attachment, version))

    for attachment, version in attachments_to_link:
        attachments.save(
            attachment.model_copy(update={"site_update_id": update.id}),
            expected_version=version,
        )
        attachment_context = context.model_copy(
            update={
                "idempotency_key": (
                    f"site-update:{update.id}:attachment:"
                    f"{sha256(attachment.id.encode('utf-8')).hexdigest()[:20]}"
                )
            }
        )
        activities.create(
            ActivityRepository.build_event(
                attachment_context,
                ActivitySpec(
                    action="attachment.linked",
                    entity_type="attachment",
                    entity_id=attachment.id,
                    summary="Linked a verified attachment to a site update.",
                    metadata={"site_update_id": update.id},
                ),
            )
        )
    saved = session.repository(SiteUpdate).create(update)
    session.repository(AgentRun).create(run)
    session.repository(OutboxMessage).create(outbox)
    return saved


def _infer_input_type(
    raw_text: str | None,
    transcript: str | None,
    attachment_ids: Sequence[str],
) -> SiteUpdateInputType:
    channel_count = sum((bool(raw_text), bool(transcript), bool(attachment_ids)))
    if channel_count > 1:
        return SiteUpdateInputType.MIXED
    if transcript:
        return SiteUpdateInputType.VOICE
    if attachment_ids:
        return SiteUpdateInputType.PHOTO
    return SiteUpdateInputType.TEXT


__all__ = [
    "EventPublisher",
    "SiteUpdateIntakeResult",
    "SiteUpdateIntakeService",
    "SiteUpdateAttachmentError",
    "SiteUpdatePublishError",
]
