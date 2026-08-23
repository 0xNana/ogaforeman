"""Bounded dependency probes used by readiness endpoints."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

from google.api_core.exceptions import NotFound

from app.config.settings import NotificationProviderName, RuntimeEnvironment, Settings


Probe = Callable[[], tuple[bool, str]]


class FirestoreQuery(Protocol):
    def limit(self, limit: int) -> "FirestoreQuery": ...

    def stream(self, *, timeout: float) -> Iterator[object]: ...


class FirestoreClient(Protocol):
    def collection(self, name: str) -> FirestoreQuery: ...


class StorageClient(Protocol):
    def list_blobs(
        self,
        bucket_or_name: str,
        *,
        max_results: int,
        timeout: float,
    ) -> Iterator[object]: ...


def configuration_probe(settings: Settings) -> Probe:
    def check() -> tuple[bool, str]:
        return True, settings.oga_env.value

    return check


def external_notification_configuration_probe(settings: Settings) -> Probe:
    def check() -> tuple[bool, str]:
        if settings.notification_provider is NotificationProviderName.GOOGLE_CHAT:
            if settings.google_chat_webhook_url is not None:
                return True, "google_chat_configured"
            return False, "google_chat_missing"
        if settings.oga_env in {
            RuntimeEnvironment.PREVIEW,
            RuntimeEnvironment.STAGING,
            RuntimeEnvironment.PRODUCTION,
        }:
            return False, "external_provider_required"
        return True, "logging_development_only"

    return check


def firestore_probe(client: FirestoreClient, *, timeout_seconds: float = 5.0) -> Probe:
    def check() -> tuple[bool, str]:
        try:
            list(client.collection("projects").limit(1).stream(timeout=timeout_seconds))
        except Exception as exc:  # readiness reports the class only, never raw dependency data
            return False, type(exc).__name__
        return True, "reachable"

    return check


def storage_probe(
    client: StorageClient,
    bucket_name: str,
    *,
    timeout_seconds: float = 5.0,
) -> Probe:
    def check() -> tuple[bool, str]:
        try:
            list(
                client.list_blobs(
                    bucket_name,
                    max_results=1,
                    timeout=timeout_seconds,
                )
            )
        except NotFound:
            return False, "bucket_not_found"
        except Exception as exc:  # readiness reports the class only, never raw dependency data
            return False, type(exc).__name__
        return True, "reachable"

    return check


__all__ = [
    "Probe",
    "configuration_probe",
    "external_notification_configuration_probe",
    "firestore_probe",
    "storage_probe",
]
