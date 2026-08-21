"""Authenticated Pub/Sub publisher with an explicit local demo adapter."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from hashlib import sha256
from threading import Lock
from typing import Protocol, cast

import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.config.settings import Settings, get_settings


_TOPIC_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._~-]{2,254}$")
_MAX_MESSAGE_BYTES = 10_000_000


class PubSubError(RuntimeError):
    """Base error for publisher configuration and delivery failures."""


class PubSubConfigurationError(PubSubError):
    pass


class PubSubPublishError(PubSubError):
    pass


class HttpResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...


class HttpSession(Protocol):
    def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
        timeout: float,
    ) -> HttpResponse: ...


class PubSubClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session: HttpSession | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("timeout_seconds must be between 0 and 60")
        self._settings = settings or get_settings()
        self._session = session
        self._session_lock = Lock()
        self._timeout_seconds = timeout_seconds

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        if not isinstance(data, bytes) or not data:
            raise ValueError("Pub/Sub message data must be non-empty bytes")
        if len(data) > _MAX_MESSAGE_BYTES:
            raise ValueError("Pub/Sub message exceeds the 10 MB service limit")
        safe_attributes = _validate_attributes(attributes or {})

        if self._settings.demo_mode:
            digest = sha256(data).hexdigest()[:24]
            return f"msg_demo_{digest}"

        topic_path = self._topic_path(topic or self._settings.pubsub_site_events_topic)
        payload: Mapping[str, object] = {
            "messages": [
                {
                    "data": base64.b64encode(data).decode("ascii"),
                    "attributes": safe_attributes,
                }
            ]
        }
        try:
            import os
            emulator_host = os.environ.get("PUBSUB_EMULATOR_HOST")
            base_url = f"http://{emulator_host}" if emulator_host else "https://pubsub.googleapis.com"
            response = self._get_session().post(
                f"{base_url}/v1/{topic_path}:publish",
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
        except Exception as exc:
            raise PubSubPublishError("Pub/Sub publish failed") from exc
        if not isinstance(result, dict):
            raise PubSubPublishError("Pub/Sub response was not an object")
        message_ids = result.get("messageIds")
        if (
            not isinstance(message_ids, list)
            or not message_ids
            or not isinstance(message_ids[0], str)
        ):
            raise PubSubPublishError("Pub/Sub response did not contain a message ID")
        return message_ids[0]

    def _topic_path(self, topic: str | None) -> str:
        if not topic:
            raise PubSubConfigurationError("PUBSUB_SITE_EVENTS_TOPIC is required")
        if topic.startswith("projects/"):
            parts = topic.split("/")
            if len(parts) != 4 or parts[2] != "topics":
                raise PubSubConfigurationError("Pub/Sub topic path is invalid")
            return topic
        if not _TOPIC_RE.fullmatch(topic):
            raise PubSubConfigurationError("Pub/Sub topic name is invalid")
        project_id = self._settings.google_cloud_project
        if not project_id:
            raise PubSubConfigurationError("GOOGLE_CLOUD_PROJECT is required")
        return f"projects/{project_id}/topics/{topic}"

    def _get_session(self) -> HttpSession:
        if self._session is not None:
            return self._session
        with self._session_lock:
            if self._session is None:
                import os
                import requests
                if os.environ.get("PUBSUB_EMULATOR_HOST"):
                    self._session = cast(HttpSession, requests.Session())
                else:
                    credentials, _project = google.auth.default(
                        scopes=("https://www.googleapis.com/auth/pubsub",)
                    )
                    self._session = cast(HttpSession, AuthorizedSession(credentials))
        if self._session is None:  # pragma: no cover - guarded by the lock above
            raise PubSubConfigurationError("Pub/Sub HTTP session could not be initialized")
        return self._session


def _validate_attributes(attributes: Mapping[str, str]) -> dict[str, str]:
    if len(attributes) > 100:
        raise ValueError("Pub/Sub messages may have at most 100 attributes")
    normalized: dict[str, str] = {}
    for key, value in attributes.items():
        if not key or len(key.encode("utf-8")) > 256:
            raise ValueError("Pub/Sub attribute keys must contain 1 to 256 bytes")
        if len(value.encode("utf-8")) > 1_024:
            raise ValueError("Pub/Sub attribute values may contain at most 1024 bytes")
        normalized[str(key)] = str(value)
    return normalized


__all__ = [
    "PubSubClient",
    "PubSubConfigurationError",
    "PubSubError",
    "PubSubPublishError",
]
