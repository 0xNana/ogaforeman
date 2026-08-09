"""Safety stop workflow branch."""

from typing import Any

from app.domain.models import AgentRun
from app.services.notifications import NotificationService
from app.workflows.runtime import RuntimeManager


def execute_safety_stop_branch(
    project_id: str,
    run_id: str,
    safety_stops: list[Any],
    runtime: RuntimeManager,
    notifications: NotificationService,
) -> AgentRun:
    """Halt autonomous actions and escalate safety issues to a qualified human."""

    for issue in safety_stops:
        notifications.queue_notification(
            project_id=project_id,
            topic="safety_escalation",
            payload={
                "message": f"Critical safety stop: {issue.description}",
                "severity": issue.severity,
            },
            deduplication_key=f"safety_{run_id}_{issue.description[:20]}",
        )

    # Mark the run as failed or paused waiting for resolution?
    # The plan says "credible safety/structural issues stop unsafe branches and notify qualified roles."
    # We pause for clarification/approval, or fail the run so it doesn't continue automatically.
    return runtime.fail_run(
        project_id, run_id, "SAFETY_STOP", "Workflow halted due to high-severity safety issue."
    )


__all__ = ["execute_safety_stop_branch"]
