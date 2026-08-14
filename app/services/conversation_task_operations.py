"""Conversational task commands composed from existing typed task services."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.conversation import (
    ConversationTaskCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    TaskOperation,
)
from app.domain.enums import TaskPriority, TaskStatus
from app.domain.models import Task
from app.repositories.interfaces import RepositoryStore
from app.repositories.interfaces import VersionConflictError
from app.repositories.tasks import TaskRepository
from app.services.tasks import (
    CreateTaskCommand,
    TaskChange,
    TaskEvidenceRejectedError,
    TaskService,
    UpdateTaskCommand,
    UpdateTaskDetailsCommand,
)


@dataclass(frozen=True, slots=True)
class ConversationTaskResult:
    task: Task
    activity_id: str
    reply: str
    duplicate: bool


class ConversationTaskService:
    def __init__(self, tasks: TaskService, store: RepositoryStore) -> None:
        self._tasks = tasks
        self._store = store

    def execute(
        self,
        access: ProjectAccessContext,
        command: ConversationTaskCommand,
        context: MutationContext,
    ) -> ConversationTaskResult:
        if command.operation is TaskOperation.CREATE:
            if not command.title:
                raise ValueError("task title is required for creation")
            assignee_id = (
                _resolved_id(command.assignee, EntityKind.PROJECT_MEMBER, "project member")
                if command.assignee is not None
                else None
            )
            change = self._tasks.create_task(
                access,
                CreateTaskCommand(
                    project_id=access.project_id,
                    title=command.title,
                    description=command.description,
                    priority=command.priority or TaskPriority.MEDIUM,
                    assigned_to=assignee_id,
                    trade=command.trade,
                    location=command.location,
                    planned_start=command.planned_start,
                    planned_end=command.planned_end,
                ),
                context,
            )
            return _result(change, f"Done. I created {change.task.title}.")

        task_id = _resolved_id(command.task, EntityKind.TASK, "task")
        current = TaskRepository(self._store).require(access, task_id)
        if command.expected_version is not None and command.expected_version != current.version:
            raise VersionConflictError(
                "the task changed after OG loaded it; review the fresh state and retry"
            )
        if command.operation is TaskOperation.COMPLETE:
            if command.negated or command.ambiguous:
                raise TaskEvidenceRejectedError(
                    "negated or ambiguous language cannot complete a task"
                )
            if not command.evidence:
                raise TaskEvidenceRejectedError("task completion requires explicit evidence")
            change = self._tasks.complete_task(
                access,
                UpdateTaskCommand(
                    project_id=access.project_id,
                    task_id=task_id,
                    expected_version=current.version,
                    target_status=TaskStatus.COMPLETED,
                    evidence=command.evidence,
                    negated=command.negated,
                    ambiguous=command.ambiguous,
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            return _result(change, f"Done. {change.task.title} is marked complete.")

        if command.operation is TaskOperation.CHANGE_STATUS:
            if command.target_status is None:
                raise ValueError("target_status is required")
            change = self._tasks.update_task(
                access,
                UpdateTaskCommand(
                    project_id=access.project_id,
                    task_id=task_id,
                    expected_version=current.version,
                    target_status=command.target_status,
                    evidence=command.evidence,
                    negated=command.negated,
                    ambiguous=command.ambiguous,
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            return _result(
                change,
                f"Done. {change.task.title} is now {change.task.status.value.replace('_', ' ')}.",
            )

        if command.operation in {TaskOperation.ASSIGN, TaskOperation.REASSIGN}:
            assignee_id = _resolved_id(
                command.assignee, EntityKind.PROJECT_MEMBER, "project member"
            )
            details = UpdateTaskDetailsCommand(
                project_id=access.project_id,
                task_id=task_id,
                expected_version=current.version,
                assigned_to=assignee_id,
                occurred_at=context.occurred_at,
            )
            change = self._tasks.update_task_details(access, details, context)
            name = command.assignee.display_name if command.assignee else "Project member"
            return _result(change, f"Done. {change.task.title} is assigned to {name}.")

        if command.operation is TaskOperation.CHANGE_PRIORITY:
            if command.priority is None:
                raise ValueError("priority is required")
            details = UpdateTaskDetailsCommand(
                project_id=access.project_id,
                task_id=task_id,
                expected_version=current.version,
                priority=command.priority,
                occurred_at=context.occurred_at,
            )
            change = self._tasks.update_task_details(access, details, context)
            return _result(
                change, f"Done. {change.task.title} is now {command.priority.value} priority."
            )

        if not command.note:
            raise ValueError("note is required")
        details = UpdateTaskDetailsCommand(
            project_id=access.project_id,
            task_id=task_id,
            expected_version=current.version,
            note=command.note,
            occurred_at=context.occurred_at,
        )
        change = self._tasks.update_task_details(access, details, context)
        return _result(change, f"Done. I added the note to {change.task.title}.")


def _resolved_id(
    resolution: EntityResolution | None,
    kind: EntityKind,
    label: str,
) -> str:
    if (
        resolution is None
        or resolution.kind is not kind
        or resolution.status is not EntityResolutionStatus.RESOLVED
        or not resolution.can_mutate
        or not resolution.entity_id
    ):
        raise ValueError(f"a resolved {label} is required")
    return resolution.entity_id


def _result(change: TaskChange, reply: str) -> ConversationTaskResult:
    return ConversationTaskResult(
        task=change.task,
        activity_id=change.activity.id,
        reply=reply,
        duplicate=change.duplicate,
    )


__all__ = ["ConversationTaskResult", "ConversationTaskService"]
