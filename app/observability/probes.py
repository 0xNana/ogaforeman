"""Bounded dependency probes used by readiness endpoints."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

from app.config.settings import Settings


Probe = Callable[[], tuple[bool, str]]


class FirestoreQuery(Protocol):
    def limit(self, limit: int) -> "FirestoreQuery": ...

    def stream(self, *, timeout: float) -> Iterator[object]: ...


class FirestoreClient(Protocol):
    def collection(self, name: str) -> FirestoreQuery: ...


class StorageBucket(Protocol):
    def exists(self, *, timeout: float) -> bool: ...


class StorageClient(Protocol):
    def bucket(self, name: str) -> StorageBucket: ...


def configuration_probe(settings: Settings) -> Probe:
    def check() -> tuple[bool, str]:
        return True, settings.oga_env.value

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
            exists = client.bucket(bucket_name).exists(timeout=timeout_seconds)
        except Exception as exc:  # readiness reports the class only, never raw dependency data
            return False, type(exc).__name__
        return (True, "reachable") if exists else (False, "bucket_not_found")

    return check


__all__ = [
    "Probe",
    "configuration_probe",
    "firestore_probe",
    "storage_probe",
]
