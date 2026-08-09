from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from app.domain.models import ProcessedEvent

from .interfaces import ProjectRepository, RepositoryStore


ResultT = TypeVar("ResultT")


class EventClaimRepository:
    """Typed transaction boundary for durable processed-event claims."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def run_transaction(
        self,
        operation: Callable[[ProjectRepository[ProcessedEvent]], ResultT],
    ) -> ResultT:
        return self._store.run_transaction(
            lambda session: operation(session.repository(ProcessedEvent))
        )
