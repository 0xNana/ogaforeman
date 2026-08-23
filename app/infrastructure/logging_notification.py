"""Development/test notification provider that never represents external delivery."""

from __future__ import annotations

import logging
from hashlib import sha256

from app.domain.notifications import DeliveryDelayNotification, NotificationDeliveryResult
from app.observability.logging import log_event


logger = logging.getLogger("ogaforeman.notifications.logging_provider")


class LoggingNotificationProvider:
    provider = "logging"
    destination_key = "0" * 24
    is_external = False

    def send_delivery_delay(
        self,
        payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        message_id = f"logging-{sha256(idempotency_key.encode()).hexdigest()[:32]}"
        log_event(
            logger,
            logging.INFO,
            "development_notification_recorded",
            "development notification recorded without external delivery",
            provider=self.provider,
            delivery_status="development_only",
            project_id=payload.project_id,
            event_id=payload.event_id,
        )
        return NotificationDeliveryResult(
            provider=self.provider,
            provider_message_id=message_id,
        )


__all__ = ["LoggingNotificationProvider"]
