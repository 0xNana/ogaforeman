"""Read-only inspection and controlled replay metadata for dead-lettered events."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.enums import ProcessedEventStatus
from app.domain.models import ProcessedEvent
from app.repositories.interfaces import RepositoryStore


@dataclass(frozen=True, slots=True)
class DeadLetterSummary:
    project_id: str
    count: int
    event_ids: tuple[str, ...]


class DeadLetterService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def list(self, project_id: str, *, limit: int = 100) -> Sequence[ProcessedEvent]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        events = self._store.repository(ProcessedEvent).list(project_id)
        return tuple(
            event for event in events if event.status is ProcessedEventStatus.DEAD_LETTERED
        )[:limit]

    def summarize(self, project_id: str) -> DeadLetterSummary:
        events = self.list(project_id, limit=100)
        return DeadLetterSummary(
            project_id=project_id,
            count=len(events),
            event_ids=tuple(event.event_id for event in events),
        )


__all__ = ["DeadLetterService", "DeadLetterSummary"]
