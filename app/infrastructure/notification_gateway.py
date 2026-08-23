"""External notification boundary implemented by production adapters and test fakes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, Protocol, runtime_checkable

from app.domain.notifications import DeliveryDelayNotification, NotificationDeliveryResult


class NotificationGatewayError(RuntimeError):
    """Base provider error that never contains provider credentials."""

    error_code = "NOTIFICATION_PROVIDER_ERROR"
    transient = False
    suppress_traceback = True


class TransientNotificationGatewayError(NotificationGatewayError):
    error_code = "NOTIFICATION_PROVIDER_TRANSIENT"
    transient = True


class PermanentNotificationGatewayError(NotificationGatewayError):
    error_code = "NOTIFICATION_PROVIDER_PERMANENT"


@runtime_checkable
class NotificationProvider(Protocol):
    provider: str
    destination_key: str
    is_external: bool

    def send_delivery_delay(
        self,
        payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        """Send one provider-idempotent delivery-delay notification."""


class RealExternalNotificationProvider(ABC):
    """Provider contract for a notification that leaves OG's infrastructure."""

    provider: str
    destination_key: str
    is_external: Literal[True] = True

    @abstractmethod
    def send_delivery_delay(
        self,
        payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        """Send one provider-idempotent delivery-delay notification."""


# Compatibility name retained for existing workflow injection points.
ProjectNotificationGateway = NotificationProvider


__all__ = [
    "NotificationGatewayError",
    "NotificationProvider",
    "PermanentNotificationGatewayError",
    "ProjectNotificationGateway",
    "RealExternalNotificationProvider",
    "TransientNotificationGatewayError",
]
