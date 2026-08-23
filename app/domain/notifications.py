"""Typed contracts for external project notifications."""

from __future__ import annotations

from datetime import date

from pydantic import AnyHttpUrl, ConfigDict, Field

from app.domain.enums import Severity
from app.domain.models import CanonicalId, DomainModel


class DeliveryDelayTaskReference(DomainModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    task_id: CanonicalId
    title: str = Field(min_length=1, max_length=300)


class DeliveryDelayNotification(DomainModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    project_name: str = Field(min_length=1, max_length=200)
    event_id: CanonicalId
    material_request_id: CanonicalId
    material_name: str = Field(min_length=1, max_length=300)
    revised_delivery_date: date
    delay_reason: str = Field(min_length=1, max_length=2_000)
    affected_tasks: tuple[DeliveryDelayTaskReference, ...] = Field(max_length=100)
    risk_severity: Severity
    issue_id: CanonicalId
    follow_up_task_id: CanonicalId
    action_taken: str = Field(min_length=1, max_length=500)
    safe_link: AnyHttpUrl | None = None


class NotificationDeliveryResult(DomainModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provider: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    provider_message_id: str = Field(min_length=1, max_length=500)


__all__ = [
    "DeliveryDelayNotification",
    "DeliveryDelayTaskReference",
    "NotificationDeliveryResult",
]
