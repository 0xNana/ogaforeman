"""Durable, replay-safe external delivery-delay notifications."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_hex
from urllib.parse import quote

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.enums import ActorType, OutboxStatus
from app.domain.events import ProjectEvent
from app.domain.models import ActivityEvent, Issue, OutboxMessage, Task
from app.domain.notifications import (
    DeliveryDelayNotification,
    DeliveryDelayTaskReference,
    NotificationDeliveryResult,
)
from app.infrastructure.notification_gateway import (
    NotificationProvider,
    NotificationGatewayError,
    PermanentNotificationGatewayError,
)
from app.observability.logging import log_event
from app.observability.metrics import metrics
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.services.routed_events import DeliveryDelayAssessment, DeliveryDelayContext


logger = logging.getLogger("ogaforeman.notifications.delivery")


class DeliveryNotificationError(RuntimeError):
    code = "DELIVERY_NOTIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class _ClaimResult:
    message: OutboxMessage
    claimed: bool


class NotificationService:
    external_message_type = "external_notification:delivery_delay"
    development_message_type = "development_notification:delivery_delay"

    def __init__(
        self,
        store: RepositoryStore,
        provider: NotificationProvider,
        *,
        max_attempts: int = 3,
        base_backoff_seconds: float = 1.0,
        claim_lease_seconds: int = 30,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        public_app_base_url: str | None = None,
    ) -> None:
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("notification max_attempts must be between 1 and 5")
        if base_backoff_seconds < 0 or base_backoff_seconds > 10:
            raise ValueError("notification base backoff must be between 0 and 10 seconds")
        if claim_lease_seconds < 5 or claim_lease_seconds > 300:
            raise ValueError("notification claim lease must be between 5 and 300 seconds")
        self._store = store
        self._provider = provider
        self.message_type = (
            self.external_message_type if provider.is_external else self.development_message_type
        )
        self._max_attempts = max_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._claim_lease_seconds = claim_lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper or time.sleep
        self._public_app_base_url = public_app_base_url.rstrip("/") if public_app_base_url else None

    def deliver(
        self,
        event: ProjectEvent,
        run_id: str,
        context: DeliveryDelayContext,
        assessment: DeliveryDelayAssessment,
        issue: Issue,
        follow_up: Task,
    ) -> OutboxMessage:
        payload = self._payload(event, context, assessment, issue, follow_up)
        message = self._queue(event, run_id, payload)
        if message.status is OutboxStatus.COMPLETED:
            return message

        while message.attempts < self._max_attempts:
            claim = self._claim(event, run_id, message.id)
            message = claim.message
            if message.status is OutboxStatus.COMPLETED:
                return message
            if message.status is OutboxStatus.DEAD_LETTERED:
                break
            if not claim.claimed:
                raise DeliveryNotificationError(
                    "delivery notification is already claimed by another worker"
                )
            try:
                result = self._provider.send_delivery_delay(
                    payload,
                    idempotency_key=message.deduplication_key,
                )
                message = self._record_success(event, run_id, message, result)
            except NotificationGatewayError as exc:
                message = self._record_failure(event, run_id, message, exc)
                if message.status is OutboxStatus.DEAD_LETTERED:
                    break
                backoff = self._base_backoff_seconds * (2 ** (message.attempts - 1))
                self._sleeper(backoff)
                continue
            except Exception:
                message = self._record_failure(
                    event,
                    run_id,
                    message,
                    PermanentNotificationGatewayError("notification provider adapter failed"),
                )
                break
            return message

        raise DeliveryNotificationError(
            message.last_error or "delivery notification did not reach its destination"
        )

    def _payload(
        self,
        event: ProjectEvent,
        context: DeliveryDelayContext,
        assessment: DeliveryDelayAssessment,
        issue: Issue,
        follow_up: Task,
    ) -> DeliveryDelayNotification:
        tasks_by_id = {task.id: task for task in context.tasks}
        affected = tuple(
            DeliveryDelayTaskReference(task_id=task_id, title=tasks_by_id[task_id].title)
            for task_id in assessment.affected_task_ids
        )
        link = None
        if self._public_app_base_url:
            link = (
                f"{self._public_app_base_url}/projects/{quote(event.project_id, safe='')}"
                f"/issues/{quote(issue.id, safe='')}"
            )
        return DeliveryDelayNotification(
            project_id=event.project_id,
            project_name=context.project.name,
            event_id=event.event_id,
            material_request_id=context.request.id,
            material_name=context.material.name,
            revised_delivery_date=str(event.payload["new_date"]),
            delay_reason=str(event.payload["reason"]),
            affected_tasks=affected,
            risk_severity=assessment.severity,
            issue_id=issue.id,
            follow_up_task_id=follow_up.id,
            action_taken=(
                "Marked the request delayed, opened a schedule risk, "
                "and created a delivery follow-up."
            ),
            safe_link=link,
        )

    def _queue(
        self,
        event: ProjectEvent,
        run_id: str,
        payload: DeliveryDelayNotification,
    ) -> OutboxMessage:
        digest = sha256(
            (
                f"{event.idempotency_key}\x00{self._provider.provider}\x00"
                f"{self._provider.destination_key}"
            ).encode("utf-8")
        ).hexdigest()
        deduplication_key = f"delivery-notification:{digest}"
        message_id = f"obx_{digest[:20]}"

        def queue(session: RepositorySession) -> OutboxMessage:
            outbox = session.repository(OutboxMessage)
            existing = outbox.get(event.project_id, message_id)
            if existing is not None:
                if (
                    existing.deduplication_key != deduplication_key
                    or existing.payload != payload.model_dump(mode="json")
                    or existing.provider != self._provider.provider
                    or existing.destination_key != self._provider.destination_key
                ):
                    raise RuntimeError("delivery notification idempotency conflict")
                return existing
            message = outbox.create(
                OutboxMessage(
                    id=message_id,
                    project_id=event.project_id,
                    message_type=self.message_type,
                    deduplication_key=deduplication_key,
                    payload=payload.model_dump(mode="json"),
                    provider=self._provider.provider,
                    destination_key=self._provider.destination_key,
                    created_at=self._clock(),
                )
            )
            self._record_activity(
                session,
                event,
                run_id,
                message,
                phase="queued",
                action=(
                    "external_notification.queued"
                    if self._provider.is_external
                    else "development_notification.queued"
                ),
                summary=(
                    "Queued an external delivery-delay notification."
                    if self._provider.is_external
                    else "Queued a development-only notification record."
                ),
                metadata={"provider": self._provider.provider, "status": "pending"},
            )
            return message

        message = self._store.run_transaction(queue)
        self._log(message, "delivery_notification_queued")
        return message

    def _claim(self, event: ProjectEvent, run_id: str, message_id: str) -> _ClaimResult:
        now = self._clock()

        def claim(session: RepositorySession) -> _ClaimResult:
            repo = session.repository(OutboxMessage)
            message = repo.require(event.project_id, message_id)
            if message.status in {OutboxStatus.COMPLETED, OutboxStatus.DEAD_LETTERED}:
                return _ClaimResult(message, False)
            if (
                message.status is OutboxStatus.PROCESSING
                and message.lease_expires_at is not None
                and message.lease_expires_at > now
            ):
                return _ClaimResult(message, False)
            if message.next_attempt_at is not None and message.next_attempt_at > now:
                return _ClaimResult(message, False)
            claimed = repo.save(
                message.model_copy(
                    update={
                        "status": OutboxStatus.PROCESSING,
                        "attempts": message.attempts + 1,
                        "claim_token": token_hex(16),
                        "claimed_at": now,
                        "lease_expires_at": now + timedelta(seconds=self._claim_lease_seconds),
                        "last_attempt_at": now,
                        "next_attempt_at": None,
                        "last_error": None,
                        "failure_kind": None,
                    }
                ),
                expected_version=message.version,
            )
            self._record_activity(
                session,
                event,
                run_id,
                claimed,
                phase=f"claim-{claimed.attempts}",
                action=(
                    "external_notification.attempted"
                    if self._provider.is_external
                    else "development_notification.attempted"
                ),
                summary=(
                    "Attempted an external delivery-delay notification."
                    if self._provider.is_external
                    else "Recorded a development-only notification attempt."
                ),
                metadata={
                    "provider": self._provider.provider,
                    "status": "processing",
                    "attempt": claimed.attempts,
                },
            )
            return _ClaimResult(claimed, True)

        result = self._store.run_transaction(claim)
        if result.claimed:
            self._log(result.message, "delivery_notification_claimed")
        return result

    def _record_failure(
        self,
        event: ProjectEvent,
        run_id: str,
        claimed: OutboxMessage,
        error: NotificationGatewayError,
    ) -> OutboxMessage:
        now = self._clock()
        terminal = not error.transient or claimed.attempts >= self._max_attempts
        status = OutboxStatus.DEAD_LETTERED if terminal else OutboxStatus.FAILED
        next_attempt_at = None
        if not terminal:
            delay = self._base_backoff_seconds * (2 ** (claimed.attempts - 1))
            next_attempt_at = now + timedelta(seconds=delay)

        def fail(session: RepositorySession) -> OutboxMessage:
            repo = session.repository(OutboxMessage)
            current = repo.require(event.project_id, claimed.id)
            if current.claim_token != claimed.claim_token:
                raise RuntimeError("delivery notification claim ownership changed")
            saved = repo.save(
                current.model_copy(
                    update={
                        "status": status,
                        "claim_token": None,
                        "lease_expires_at": None,
                        "next_attempt_at": next_attempt_at,
                        "last_error": error.error_code,
                        "failure_kind": "transient" if error.transient else "permanent",
                        "processed_at": now if terminal else None,
                    }
                ),
                expected_version=current.version,
            )
            self._record_activity(
                session,
                event,
                run_id,
                saved,
                phase=f"failure-{saved.attempts}",
                action=(
                    (
                        "external_notification.failed"
                        if terminal
                        else "external_notification.retry_scheduled"
                    )
                    if self._provider.is_external
                    else "development_notification.failed"
                ),
                summary=(
                    (
                        "External delivery-delay notification failed permanently."
                        if terminal
                        else "Scheduled an external delivery-delay notification retry."
                    )
                    if self._provider.is_external
                    else "Development-only notification recording failed."
                ),
                metadata={
                    "provider": self._provider.provider,
                    "status": saved.status.value,
                    "attempt": saved.attempts,
                    "error_code": error.error_code,
                },
            )
            return saved

        message = self._store.run_transaction(fail)
        self._log(message, "delivery_notification_failed", error_code=error.error_code)
        if self._provider.is_external:
            metrics.increment(
                "external_notification_attempts_total",
                labels={"provider": self._provider.provider, "outcome": "failed"},
            )
        return message

    def _record_success(
        self,
        event: ProjectEvent,
        run_id: str,
        claimed: OutboxMessage,
        result: NotificationDeliveryResult,
    ) -> OutboxMessage:
        if result.provider != self._provider.provider:
            raise PermanentNotificationGatewayError("notification provider identity mismatch")
        now = self._clock()

        def complete(session: RepositorySession) -> OutboxMessage:
            repo = session.repository(OutboxMessage)
            current = repo.require(event.project_id, claimed.id)
            if current.claim_token != claimed.claim_token:
                raise RuntimeError("delivery notification claim ownership changed")
            saved = repo.save(
                current.model_copy(
                    update={
                        "status": OutboxStatus.COMPLETED,
                        "claim_token": None,
                        "lease_expires_at": None,
                        "provider_message_id": result.provider_message_id,
                        "processed_at": now,
                        "next_attempt_at": None,
                        "last_error": None,
                        "failure_kind": None,
                    }
                ),
                expected_version=current.version,
            )
            self._record_activity(
                session,
                event,
                run_id,
                saved,
                phase="sent",
                action=(
                    "external_notification.sent"
                    if self._provider.is_external
                    else "development_notification.recorded"
                ),
                summary=(
                    "Sent the delivery-delay notification to the external destination."
                    if self._provider.is_external
                    else "Recorded the development-only delivery-delay notification."
                ),
                metadata={
                    "provider": self._provider.provider,
                    "status": "completed",
                    "attempt": saved.attempts,
                },
            )
            return saved

        message = self._store.run_transaction(complete)
        self._log(message, "delivery_notification_sent")
        if self._provider.is_external:
            metrics.increment(
                "external_notification_attempts_total",
                labels={"provider": self._provider.provider, "outcome": "succeeded"},
            )
        return message

    @staticmethod
    def _record_activity(
        session: RepositorySession,
        event: ProjectEvent,
        run_id: str,
        message: OutboxMessage,
        *,
        phase: str,
        action: str,
        summary: str,
        metadata: dict[str, object],
    ) -> None:
        context = MutationContext(
            project_id=event.project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=event.event_id,
            agent_run_id=run_id,
            idempotency_key=f"notify:{message.id}:{phase}",
            occurred_at=datetime.now(UTC),
        )
        activity = ActivityRepository.build_event(
            context,
            ActivitySpec(
                action=action,
                entity_type="outbox_message",
                entity_id=message.id,
                summary=summary,
                metadata=metadata,
            ),
        )
        repo = session.repository(ActivityEvent)
        existing = repo.get(event.project_id, activity.id)
        if existing is None:
            repo.create(activity)
        else:
            ActivityRepository.ensure_replay_matches(existing, activity)

    def _log(
        self,
        message: OutboxMessage,
        event_name: str,
        *,
        error_code: str | None = None,
    ) -> None:
        log_event(
            logger,
            (logging.ERROR if message.status is OutboxStatus.DEAD_LETTERED else logging.INFO),
            event_name,
            (
                "external delivery-delay notification state changed"
                if self._provider.is_external
                else "development-only delivery-delay notification state changed"
            ),
            provider=self._provider.provider,
            outbox_item_id=message.id,
            delivery_status=message.status.value,
            retry_attempt=message.attempts,
            error_code=error_code,
        )


DeliveryNotificationService = NotificationService


__all__ = [
    "DeliveryNotificationError",
    "DeliveryNotificationService",
    "NotificationService",
]
