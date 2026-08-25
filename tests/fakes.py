"""Explicit test-only external boundary fakes."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from app.domain.notifications import DeliveryDelayNotification, NotificationDeliveryResult
from app.infrastructure.notification_gateway import NotificationGatewayError


class FakeNotificationProvider:
    provider = "google_chat"
    destination_key = "a" * 24
    is_enabled = True
    is_external = True

    def __init__(self, outcomes: Iterable[NotificationGatewayError | None] = ()) -> None:
        self._outcomes = list(outcomes)
        self.attempts: list[tuple[DeliveryDelayNotification, str]] = []
        self.logical_sends: dict[str, str] = {}

    def send_delivery_delay(
        self,
        payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        self.attempts.append((payload, idempotency_key))
        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if outcome is not None:
                raise outcome
        provider_message_id = self.logical_sends.setdefault(
            idempotency_key,
            f"spaces/test/messages/{sha256(idempotency_key.encode()).hexdigest()[:16]}",
        )
        return NotificationDeliveryResult(
            provider=self.provider,
            provider_message_id=provider_message_id,
        )


FakeProjectNotificationGateway = FakeNotificationProvider


__all__ = ["FakeNotificationProvider", "FakeProjectNotificationGateway"]
