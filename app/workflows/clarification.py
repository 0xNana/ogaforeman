"""Clarification workflow branch."""

from typing import Any

from app.domain.models import AgentRun
from app.services.notifications import NotificationService
from app.workflows.runtime import RuntimeManager


def execute_clarification_branch(
    project_id: str,
    run_id: str,
    clarification_facts: list[Any],
    runtime: RuntimeManager,
    notifications: NotificationService,
) -> AgentRun:
    """Pause the workflow to ask for clarification from the user."""

    # Send a notification for each clarification needed (or aggregate them)
    for fact in clarification_facts:
        entity_name = getattr(fact, "task_name", None) or getattr(fact, "material_name", "entity")
        notifications.queue_notification(
            project_id=project_id,
            topic="clarification_needed",
            payload={"message": f"Please clarify your update regarding '{entity_name}'."},
            deduplication_key=f"clarify_{run_id}_{entity_name}",
        )

    return runtime.pause_for_clarification(project_id, run_id, "clarification_needed")


__all__ = ["execute_clarification_branch"]
