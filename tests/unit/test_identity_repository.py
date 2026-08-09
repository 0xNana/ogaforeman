from __future__ import annotations

from typing import Any

from google.api_core.exceptions import Aborted, AlreadyExists
from google.api_core.retry import Retry

from app.domain.models import User
from app.repositories.membership import FirestoreIdentityRepository


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _Document:
    def __init__(self, *, aborted_attempts: int = 0) -> None:
        self.data: dict[str, Any] | None = None
        self.aborted_attempts = aborted_attempts
        self.create_attempts = 0

    def create(self, data: dict[str, Any], *, retry: Retry | None = None) -> None:
        operation = retry(self._create_once) if retry is not None else self._create_once
        operation(data)

    def _create_once(self, data: dict[str, Any]) -> None:
        self.create_attempts += 1
        if self.create_attempts <= self.aborted_attempts:
            raise Aborted("transaction lock timeout")
        if self.data is not None:
            raise AlreadyExists("user already exists")
        self.data = data

    def get(self) -> _Snapshot:
        return _Snapshot(self.data)


class _Collection:
    def __init__(self, document: _Document) -> None:
        self._document = document

    def document(self, document_id: str) -> _Document:
        assert document_id == "usr_bootstrap123"
        return self._document


class _CreateOnlyClient:
    def __init__(self, *, aborted_attempts: int = 0) -> None:
        self.document = _Document(aborted_attempts=aborted_attempts)

    def collection(self, name: str) -> _Collection:
        assert name == "users"
        return _Collection(self.document)

    def transaction(self) -> None:
        raise AssertionError("deterministic identity provisioning must not open a transaction")


def test_firestore_identity_provision_converges_via_atomic_create() -> None:
    client = _CreateOnlyClient()
    repository = FirestoreIdentityRepository(client)  # type: ignore[arg-type]
    user = User(
        id="usr_bootstrap123",
        identity_subject="firebase-subject-123",
        display_name="Site Foreman",
        email="foreman@example.com",
    )

    first = repository.provision(user)
    replay = repository.provision(user.model_copy(update={"display_name": "Concurrent caller"}))

    assert first == user
    assert replay == user
    assert client.document.data == user.model_dump(mode="python")


def test_firestore_identity_provision_retries_transient_lock_abort() -> None:
    client = _CreateOnlyClient(aborted_attempts=1)
    repository = FirestoreIdentityRepository(client)  # type: ignore[arg-type]
    user = User(
        id="usr_bootstrap123",
        identity_subject="firebase-subject-123",
        display_name="Site Foreman",
        email="foreman@example.com",
    )

    created = repository.provision(user)

    assert created == user
    assert client.document.create_attempts == 2
    assert client.document.data == user.model_dump(mode="python")
