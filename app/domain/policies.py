from collections.abc import Iterable
from typing import Any

from .enums import ApprovalStatus, MaterialRequestStatus, TaskStatus
from .models import Task


class InvalidTransitionError(ValueError):
    """A requested domain state transition is not allowed by policy."""


_TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PROPOSED: frozenset({TaskStatus.PLANNED, TaskStatus.CANCELLED}),
    TaskStatus.PLANNED: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
    ),
    TaskStatus.IN_PROGRESS: frozenset(
        {TaskStatus.BLOCKED, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.BLOCKED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def ensure_task_transition(
    current: TaskStatus,
    target: TaskStatus,
    *,
    human_correction: bool = False,
    reconciled_completion: bool = False,
) -> None:
    if current is target:
        return

    if human_correction:
        if current is TaskStatus.COMPLETED and target is TaskStatus.IN_PROGRESS:
            return
        raise InvalidTransitionError(
            f"human correction cannot transition task from {current} to {target}"
        )

    # A trusted site report may discover work completed before project tracking
    # ever recorded it as in progress. Keep this exception explicit so ordinary
    # task commands retain the normal transition policy.
    if reconciled_completion:
        if current is TaskStatus.PLANNED and target is TaskStatus.COMPLETED:
            return

    if target not in _TASK_TRANSITIONS[current]:
        raise InvalidTransitionError(f"task cannot transition from {current} to {target}")


_APPROVAL_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    ),
    ApprovalStatus.APPROVED: frozenset(),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.EXPIRED: frozenset(),
    ApprovalStatus.CANCELLED: frozenset(),
}


def ensure_approval_transition(current: ApprovalStatus, target: ApprovalStatus) -> None:
    if current is target:
        return
    if target not in _APPROVAL_TRANSITIONS[current]:
        raise InvalidTransitionError(f"approval cannot transition from {current} to {target}")


_MATERIAL_REQUEST_TRANSITIONS: dict[MaterialRequestStatus, frozenset[MaterialRequestStatus]] = {
    MaterialRequestStatus.PROPOSED: frozenset(
        {MaterialRequestStatus.AWAITING_APPROVAL, MaterialRequestStatus.CANCELLED}
    ),
    MaterialRequestStatus.AWAITING_APPROVAL: frozenset(
        {
            MaterialRequestStatus.APPROVED,
            MaterialRequestStatus.REJECTED,
            MaterialRequestStatus.CANCELLED,
        }
    ),
    MaterialRequestStatus.APPROVED: frozenset(
        {
            MaterialRequestStatus.SUBMITTED,
            MaterialRequestStatus.DELAYED,
            MaterialRequestStatus.CANCELLED,
        }
    ),
    MaterialRequestStatus.REJECTED: frozenset(),
    MaterialRequestStatus.SUBMITTED: frozenset(
        {
            MaterialRequestStatus.CONFIRMED,
            MaterialRequestStatus.DELAYED,
            MaterialRequestStatus.CANCELLED,
        }
    ),
    MaterialRequestStatus.CONFIRMED: frozenset(
        {
            MaterialRequestStatus.DELAYED,
            MaterialRequestStatus.DELIVERED,
            MaterialRequestStatus.CANCELLED,
        }
    ),
    MaterialRequestStatus.DELAYED: frozenset(
        {MaterialRequestStatus.CONFIRMED, MaterialRequestStatus.DELIVERED}
    ),
    MaterialRequestStatus.DELIVERED: frozenset(),
    MaterialRequestStatus.CANCELLED: frozenset(),
}


def ensure_material_request_transition(
    current: MaterialRequestStatus,
    target: MaterialRequestStatus,
) -> None:
    if current is target:
        return
    if target not in _MATERIAL_REQUEST_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"material request cannot transition from {current} to {target}"
        )


def validate_task_dependency_graph(tasks: Iterable[Task]) -> None:
    task_list = list(tasks)
    if not task_list:
        return

    project_ids = {task.project_id for task in task_list}
    if len(project_ids) != 1:
        raise ValueError("all tasks in a dependency graph must belong to the same project")

    tasks_by_id = {task.id: task for task in task_list}
    if len(tasks_by_id) != len(task_list):
        raise ValueError("dependency graph contains duplicate task IDs")

    for task in task_list:
        for dependency_id in task.dependency_ids:
            if dependency_id not in tasks_by_id:
                raise ValueError(
                    f"task {task.id} references missing task dependency {dependency_id}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError("task dependency graph contains a cycle")
        if task_id in visited:
            return

        visiting.add(task_id)
        for dependency_id in tasks_by_id[task_id].dependency_ids:
            visit(dependency_id)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks_by_id:
        visit(task_id)


def is_actionable_fact(fact: Any) -> bool:
    if getattr(fact, "is_negated", False):
        return False
    if getattr(fact, "clarification_needed", None):
        return False
    confidence = getattr(fact, "confidence", None)
    if confidence and str(confidence).lower() == "low":
        return False
    return True


def assess_safety_stop_policy(safety_issues: Iterable[Any]) -> bool:
    for issue in safety_issues:
        severity = getattr(issue, "severity", "")
        if severity and str(severity).lower() in {"high", "critical"}:
            return True
    return False
