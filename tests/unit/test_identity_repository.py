from __future__ import annotations

from typing import Any

from google.api_core.exceptions import AlreadyExists

from app.domain.models import User
from app.repositories.membership import FirestoreIdentityRepository


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _Document:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None

    def create(self, data: dict[str, Any]) -> None:
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
    def __init__(self) -> None:
        self.document = _Document()

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
