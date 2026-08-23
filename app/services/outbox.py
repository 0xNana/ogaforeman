from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
import hashlib

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.models import ActivityEvent, OutboxMessage, OutboxStatus
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore

logger = logging.getLogger(__name__)
ResultT = TypeVar("ResultT")


class OutboxService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def queue(
        self,
        project_id: str,
        message_type: str,
        payload: dict[str, Any],
        deduplication_key: str,
    ) -> OutboxMessage:
        hash_suffix = hashlib.sha256(deduplication_key.encode("utf-8")).hexdigest()[:20]
        message_id = f"obx_{hash_suffix}"

        def _queue(repo: ProjectRepository[OutboxMessage]) -> OutboxMessage:
            existing = repo.get(project_id, message_id)
            if existing:
                return existing
            message = OutboxMessage(
                id=message_id,
                project_id=project_id,
                message_type=message_type,
                deduplication_key=deduplication_key,
                payload=payload,
                status=OutboxStatus.PENDING,
            )
            return repo.create(message)

        return self._store.run_transaction(
            lambda session: _queue(session.repository(OutboxMessage))
        )

    def process(
        self,
        project_id: str,
        message_id: str,
        handler: Callable[[OutboxMessage], None],
        *,
        audit_context: MutationContext | None = None,
    ) -> OutboxMessage:
        def _claim(session: RepositorySession) -> OutboxMessage:
            repo = session.repository(OutboxMessage)
            msg = repo.require(project_id, message_id)
            if msg.status == OutboxStatus.COMPLETED:
                return msg

            msg = msg.model_copy(
                update={
                    "status": OutboxStatus.PROCESSING,
                    "attempts": msg.attempts + 1,
                }
            )
            saved = repo.save(msg, expected_version=msg.version)
            self._record_activity(
                session,
                audit_context,
                saved,
                phase=f"claim-{saved.attempts}",
                action="outbox.claimed",
                summary="Claimed an event for publication.",
            )
            return saved

        message = self._store.run_transaction(_claim)

        if message.status == OutboxStatus.COMPLETED:
            return message

        try:
            handler(message)
        except Exception as exc:
            error_summary = str(exc)[:5_000]
            error_code = type(exc).__name__
            if getattr(exc, "suppress_traceback", False):
                logger.warning("Outbox message %s failed: %s", message_id, error_summary)
            else:
                logger.exception("Outbox message %s failed", message_id)

            def _fail(session: RepositorySession) -> OutboxMessage:
                repo = session.repository(OutboxMessage)
                msg = repo.require(project_id, message_id)
                saved = repo.save(
                    msg.model_copy(
                        update={
                            "status": OutboxStatus.FAILED,
                            "last_error": error_summary,
                        }
                    ),
                    expected_version=msg.version,
                )
                self._record_activity(
                    session,
                    audit_context,
                    saved,
                    phase=f"failure-{saved.attempts}",
                    action="outbox.publication_failed",
                    summary="Event publication failed and remains retryable.",
                    error_code=error_code,
                )
                return saved

            return self._store.run_transaction(_fail)

        def _complete(session: RepositorySession) -> OutboxMessage:
            repo = session.repository(OutboxMessage)
            msg = repo.require(project_id, message_id)
            saved = repo.save(
                msg.model_copy(
                    update={
                        "status": OutboxStatus.COMPLETED,
                        "processed_at": datetime.now(UTC),
                    }
                ),
                expected_version=msg.version,
            )
            self._record_activity(
                session,
                audit_context,
                saved,
                phase="published",
                action="outbox.published",
                summary="Published an event for worker processing.",
            )
            return saved

        return self._store.run_transaction(_complete)

    @staticmethod
    def _record_activity(
        session: RepositorySession,
        context: MutationContext | None,
        message: OutboxMessage,
        *,
        phase: str,
        action: str,
        summary: str,
        error_code: str | None = None,
    ) -> None:
        if context is None:
            return
        key_digest = hashlib.sha256(context.idempotency_key.encode()).hexdigest()
        stage_context = context.model_copy(
            update={
                "idempotency_key": f"outbox:{key_digest}:{message.id}:{phase}",
                "occurred_at": datetime.now(UTC),
            }
        )
        metadata: dict[str, Any] = {
            "message_type": message.message_type,
            "status": message.status.value,
            "attempt": message.attempts,
        }
        if error_code is not None:
            metadata["error_code"] = error_code
        activity = ActivityRepository.build_event(
            stage_context,
            ActivitySpec(
                action=action,
                entity_type="outbox_message",
                entity_id=message.id,
                summary=summary,
                metadata=metadata,
            ),
        )
        repository = session.repository(ActivityEvent)
        existing = repository.get(message.project_id, activity.id)
        if existing is None:
            repository.create(activity)
        else:
            ActivityRepository.ensure_replay_matches(existing, activity)
