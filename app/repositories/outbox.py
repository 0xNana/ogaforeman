from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from app.domain.models import OutboxMessage
from app.repositories.interfaces import ProjectRepository, RepositoryStore

ResultT = TypeVar("ResultT")


class OutboxRepository:
    """Typed transaction boundary for outbox messages."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def run_transaction(
        self,
        operation: Callable[[ProjectRepository[OutboxMessage]], ResultT],
    ) -> ResultT:
        return self._store.run_transaction(
            lambda session: operation(session.repository(OutboxMessage))
        )
