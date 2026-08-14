"""Typed task mutation tools."""

from __future__ import annotations

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.services.tasks import (
    CreateBlockerFollowUpCommand,
    CreateTaskCommand,
    TaskChange,
    TaskService,
    UpdateTaskCommand,
    UpdateTaskDetailsCommand,
)


class TaskTools:
    """Dependency-injected task tools used by workflows and agents."""

    def __init__(self, service: TaskService, access: ProjectAccessContext) -> None:
        self._service = service
        self._access = access

    def update_task_progress(
        self,
        command: UpdateTaskCommand,
        context: MutationContext,
    ) -> TaskChange:
        return self._service.update_task(self._access, command, context)

    def create_task(
        self,
        command: CreateTaskCommand,
        context: MutationContext,
    ) -> TaskChange:
        return self._service.create_task(self._access, command, context)

    def create_blocker_follow_up(
        self,
        command: CreateBlockerFollowUpCommand,
        context: MutationContext,
    ) -> TaskChange:
        return self._service.create_blocker_follow_up(self._access, command, context)

    def complete_task(
        self,
        command: UpdateTaskCommand,
        context: MutationContext,
    ) -> TaskChange:
        return self._service.complete_task(self._access, command, context)

    def update_task_details(
        self,
        command: UpdateTaskDetailsCommand,
        context: MutationContext,
    ) -> TaskChange:
        return self._service.update_task_details(self._access, command, context)


def update_task_progress(
    command: UpdateTaskCommand,
    *,
    service: TaskService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> TaskChange:
    return service.update_task(access, command, context)


def create_task(
    command: CreateTaskCommand,
    *,
    service: TaskService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> TaskChange:
    return service.create_task(access, command, context)


def update_task_details(
    command: UpdateTaskDetailsCommand,
    *,
    service: TaskService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> TaskChange:
    return service.update_task_details(access, command, context)


def complete_task(
    command: UpdateTaskCommand,
    *,
    service: TaskService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> TaskChange:
    return service.complete_task(access, command, context)


__all__ = [
    "TaskTools",
    "complete_task",
    "create_task",
    "update_task_details",
    "update_task_progress",
]
