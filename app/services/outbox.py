from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
import hashlib

from app.domain.models import OutboxMessage, OutboxStatus
from app.repositories.interfaces import ProjectRepository, RepositoryStore

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
    ) -> OutboxMessage:
        def _claim(repo: ProjectRepository[OutboxMessage]) -> OutboxMessage:
            msg = repo.require(project_id, message_id)
            if msg.status == OutboxStatus.COMPLETED:
                return msg

            msg = msg.model_copy(
                update={
                    "status": OutboxStatus.PROCESSING,
                    "attempts": msg.attempts + 1,
                }
            )
            return repo.save(msg, expected_version=msg.version)

        message = self._store.run_transaction(
            lambda session: _claim(session.repository(OutboxMessage))
        )

        if message.status == OutboxStatus.COMPLETED:
            return message

        try:
            handler(message)
        except Exception as exc:
            error_summary = str(exc)[:5_000]
            if getattr(exc, "suppress_traceback", False):
                logger.warning("Outbox message %s failed: %s", message_id, error_summary)
            else:
                logger.exception("Outbox message %s failed", message_id)

            def _fail(repo: ProjectRepository[OutboxMessage]) -> OutboxMessage:
                msg = repo.require(project_id, message_id)
                return repo.save(
                    msg.model_copy(
                        update={
                            "status": OutboxStatus.FAILED,
                            "last_error": error_summary,
                        }
                    ),
                    expected_version=msg.version,
                )

            return self._store.run_transaction(
                lambda session: _fail(session.repository(OutboxMessage))
            )

        def _complete(repo: ProjectRepository[OutboxMessage]) -> OutboxMessage:
            msg = repo.require(project_id, message_id)
            return repo.save(
                msg.model_copy(
                    update={
                        "status": OutboxStatus.COMPLETED,
                        "processed_at": datetime.now(UTC),
                    }
                ),
                expected_version=msg.version,
            )

        return self._store.run_transaction(
            lambda session: _complete(session.repository(OutboxMessage))
        )
