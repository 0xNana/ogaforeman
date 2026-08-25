"""Explicit notification provider that performs no external delivery."""

from __future__ import annotations

from app.domain.notifications import DeliveryDelayNotification, NotificationDeliveryResult


class DisabledNotificationProvider:
    provider = "disabled"
    destination_key = "f" * 24
    is_enabled = False
    is_external = False

    def send_delivery_delay(
        self,
        payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        del payload, idempotency_key
        raise RuntimeError("disabled notification provider cannot send")


__all__ = ["DisabledNotificationProvider"]
