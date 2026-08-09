"""Durable blocker workflow entry point."""

from app.domain.events import EventType, ProjectEvent
from app.repositories.interfaces import RepositoryStore
from app.services.routed_events import RoutedEventExecution, RoutedEventExecutor


def run_blockers_workflow(
    event: ProjectEvent,
    *,
    store: RepositoryStore,
) -> RoutedEventExecution:
    if event.event_type not in {
        EventType.TASK_BLOCKED,
        EventType.TASK_OVERDUE,
        EventType.DELIVERY_DELAYED,
    }:
        raise ValueError("blocker workflow requires a blocker or delay event")
    return RoutedEventExecutor(store).execute(event)
