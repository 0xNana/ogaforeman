"""Durable daily-brief workflow entry point."""

from app.domain.events import EventType, ProjectEvent
from app.repositories.interfaces import RepositoryStore
from app.services.routed_events import RoutedEventExecution, RoutedEventExecutor


def run_daily_brief_workflow(
    event: ProjectEvent,
    *,
    store: RepositoryStore,
) -> RoutedEventExecution:
    if event.event_type is not EventType.DAILY_BRIEF_REQUESTED:
        raise ValueError("daily brief workflow requires DAILY_BRIEF_REQUESTED")
    return RoutedEventExecutor(store).execute(event)
