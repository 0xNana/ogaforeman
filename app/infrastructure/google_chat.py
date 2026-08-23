"""Google Chat incoming-webhook notification adapter."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

import requests

from app.domain.notifications import DeliveryDelayNotification, NotificationDeliveryResult
from app.infrastructure.notification_gateway import (
    PermanentNotificationGatewayError,
    RealExternalNotificationProvider,
    TransientNotificationGatewayError,
)


_CHAT_PATH = re.compile(r"^/v1/spaces/[A-Za-z0-9_-]+/messages$")
_TRANSIENT_STATUS = {408, 409, 425, 429}


class ChatResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


class ChatSession(Protocol):
    def post(
        self,
        url: str,
        *,
        json: dict[str, str],
        timeout: float,
        allow_redirects: bool,
    ) -> ChatResponse: ...


class GoogleChatNotificationProvider(RealExternalNotificationProvider):
    provider = "google_chat"
    is_external = True

    def __init__(
        self,
        webhook_url: str,
        *,
        session: ChatSession | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("Google Chat timeout must be between 0 and 30 seconds")
        parsed = urlsplit(webhook_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if (
            parsed.scheme != "https"
            or parsed.hostname != "chat.googleapis.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or _CHAT_PATH.fullmatch(parsed.path) is None
            or not query.get("key")
            or not query.get("token")
        ):
            raise ValueError("Google Chat webhook URL is invalid")
        self._webhook_url = webhook_url
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds
        self.destination_key = sha256(
            f"{parsed.hostname}{parsed.path}".encode("utf-8")
        ).hexdigest()[:24]

    def send_delivery_delay(
        self,
        payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        message_key = sha256(idempotency_key.encode("utf-8")).hexdigest()
        request_id = str(uuid5(NAMESPACE_URL, idempotency_key))
        message_id = f"client-{message_key[:40]}"
        url = _with_idempotency(self._webhook_url, request_id, message_id)
        try:
            response = self._session.post(
                url,
                json={"text": _format_delivery_delay(payload)},
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise TransientNotificationGatewayError(
                "Google Chat notification transport failed"
            ) from exc
        if response.status_code in _TRANSIENT_STATUS or response.status_code >= 500:
            raise TransientNotificationGatewayError(
                f"Google Chat returned transient HTTP {response.status_code}"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise PermanentNotificationGatewayError(
                f"Google Chat returned permanent HTTP {response.status_code}"
            )
        try:
            body = response.json()
        except (TypeError, ValueError) as exc:
            raise PermanentNotificationGatewayError(
                "Google Chat returned an invalid success response"
            ) from exc
        provider_id = body.get("name") if isinstance(body, dict) else None
        if isinstance(provider_id, str) and (
            len(provider_id) > 500
            or re.fullmatch(r"spaces/[^/\s]+/messages/[^/\s]+", provider_id) is None
        ):
            raise PermanentNotificationGatewayError(
                "Google Chat returned an invalid message identity"
            )
        return NotificationDeliveryResult(
            provider=self.provider,
            provider_message_id=provider_id if isinstance(provider_id, str) else message_id,
        )


def _with_idempotency(webhook_url: str, request_id: str, message_id: str) -> str:
    parsed = urlsplit(webhook_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"requestId": request_id, "messageId": message_id})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _format_delivery_delay(payload: DeliveryDelayNotification) -> str:
    tasks = (
        ", ".join(
            f"{_safe_chat_text(task.title)} ({task.task_id})" for task in payload.affected_tasks
        )
        or "No linked tasks"
    )
    lines = [
        "Delivery delay",
        f"Project: {_safe_chat_text(payload.project_name)} ({payload.project_id})",
        f"Event: {payload.event_id}",
        f"Material: {_safe_chat_text(payload.material_name)}",
        f"Request: {payload.material_request_id}",
        f"Revised delivery: {payload.revised_delivery_date.isoformat()}",
        f"Reason: {_safe_chat_text(payload.delay_reason)}",
        f"Risk: {payload.risk_severity.value}",
        f"Affected tasks: {tasks}",
        f"OG action: {_safe_chat_text(payload.action_taken)}",
        f"Reference: risk {payload.issue_id}; follow-up {payload.follow_up_task_id}",
    ]
    if payload.safe_link is not None:
        lines.append(f"Open issue: {payload.safe_link}")
    rendered = "\n".join(lines)
    if len(rendered.encode("utf-8")) > 30_000:
        raise PermanentNotificationGatewayError("Google Chat notification is too large")
    return rendered


def _safe_chat_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("<", "[").replace(">", "]")


# Compatibility alias for existing imports while the provider vocabulary migrates.
GoogleChatNotificationGateway = GoogleChatNotificationProvider


__all__ = ["GoogleChatNotificationGateway", "GoogleChatNotificationProvider"]
