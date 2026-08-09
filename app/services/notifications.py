from __future__ import annotations

import logging
from typing import Any
from app.domain.models import OutboxMessage
from app.services.outbox import OutboxService

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, outbox: OutboxService) -> None:
        self._outbox = outbox

    def queue_notification(
        self,
        project_id: str,
        topic: str,
        payload: dict[str, Any],
        deduplication_key: str,
    ) -> OutboxMessage:
        return self._outbox.queue(
            project_id=project_id,
            message_type=f"notification:{topic}",
            payload=payload,
            deduplication_key=deduplication_key,
        )

    def process_notification(
        self,
        project_id: str,
        message_id: str,
    ) -> OutboxMessage:
        def _send(message: OutboxMessage) -> None:
            # Simulate sending notification
            logger.info("Sending notification: %s", message.payload)

        return self._outbox.process(project_id, message_id, _send)
