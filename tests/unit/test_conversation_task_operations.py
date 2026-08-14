from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, RoleRequiredError
from app.domain.conversation import (
    ConversationTaskCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    TaskOperation,
)
from app.domain.enums import ActorType, MemberRole, MemberStatus, TaskPriority, TaskStatus
from app.domain.models import ActivityEvent, ProjectMember, Task
from app.repositories.memory import InMemoryRepositoryStore
from app.repositories.interfaces import VersionConflictError
from app.services.conversation_task_operations import ConversationTaskService
from app.services.tasks import TaskEvidenceRejectedError, TaskService


NOW = datetime(2026, 8, 13, 15, tzinfo=UTC)
PROJECT_ID = "prj_tasks123"


def access(role: MemberRole = MemberRole.MANAGER) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager-subject"),
        project_id=PROJECT_ID,
        role=role,
    )


def context(key: str) -> MutationContext:
    return MutationContext(
        project_id=PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        idempotency_key=key,
        occurred_at=NOW,
    )


def resolution(
    entity_id: str = "tsk_plumbing123",
    *,
    kind: EntityKind = EntityKind.TASK,
    status: EntityResolutionStatus = EntityResolutionStatus.RESOLVED,
) -> EntityResolution:
    return EntityResolution(
        kind=kind,
        reference="plumbing",
        status=status,
        entity_id=entity_id if status is EntityResolutionStatus.RESOLVED else None,
        display_name="Ground-floor plumbing" if status is EntityResolutionStatus.RESOLVED else None,
        match_method="exact" if status is EntityResolutionStatus.RESOLVED else None,
        can_mutate=status is EntityResolutionStatus.RESOLVED,
    )


def store() -> InMemoryRepositoryStore:
    result = InMemoryRepositoryStore()
    result.repository(Task).create(
        Task(
            id="tsk_plumbing123",
            project_id=PROJECT_ID,
            title="Ground-floor plumbing",
            status=TaskStatus.IN_PROGRESS,
        )
    )
    result.repository(ProjectMember).create(
        ProjectMember(
            project_id=PROJECT_ID,
            user_id="usr_kofi123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    return result


def test_explicit_completion_uses_existing_typed_service_and_replays_once() -> None:
    task_store = store()
    service = ConversationTaskService(TaskService(task_store), task_store)
    command = ConversationTaskCommand(
        operation=TaskOperation.COMPLETE,
        task=resolution(),
        evidence="Mark plumbing complete.",
    )

    first = service.execute(access(), command, context("og:complete:plumbing"))
    replay = service.execute(access(), command, context("og:complete:plumbing"))

    assert first.task.status is TaskStatus.COMPLETED
    assert first.reply == "Done. Ground-floor plumbing is marked complete."
    assert first.duplicate is False
    assert replay.duplicate is True
    assert len(task_store.repository(ActivityEvent).list(PROJECT_ID)) == 1


@pytest.mark.parametrize("evidence", ["Plumbing is not complete.", "Plumbing is basically done."])
def test_negated_or_ambiguous_completion_never_mutates(evidence: str) -> None:
    task_store = store()
    command = ConversationTaskCommand(
        operation=TaskOperation.COMPLETE,
        task=resolution(),
        evidence=evidence,
        negated="not complete" in evidence,
        ambiguous="basically" in evidence,
    )

    with pytest.raises(TaskEvidenceRejectedError):
        ConversationTaskService(TaskService(task_store), task_store).execute(
            access(), command, context("og:unsafe-completion")
        )

    assert task_store.repository(Task).require(PROJECT_ID, "tsk_plumbing123").version == 0
    assert task_store.repository(ActivityEvent).list(PROJECT_ID) == ()


def test_assignment_priority_and_note_persist_atomically_with_activity() -> None:
    task_store = store()
    service = ConversationTaskService(TaskService(task_store), task_store)
    member = EntityResolution(
        kind=EntityKind.PROJECT_MEMBER,
        reference="Kofi",
        status=EntityResolutionStatus.RESOLVED,
        entity_id="usr_kofi123",
        display_name="Kofi Mensah",
        match_method="exact",
        can_mutate=True,
    )

    assigned = service.execute(
        access(),
        ConversationTaskCommand(
            operation=TaskOperation.ASSIGN,
            task=resolution(),
            assignee=member,
        ),
        context("og:assign:plumbing:kofi"),
    )
    prioritized = service.execute(
        access(),
        ConversationTaskCommand(
            operation=TaskOperation.CHANGE_PRIORITY,
            task=resolution(),
            priority=TaskPriority.HIGH,
        ),
        context("og:priority:plumbing:high"),
    )
    noted = service.execute(
        access(),
        ConversationTaskCommand(
            operation=TaskOperation.ADD_NOTE,
            task=resolution(),
            note="Waiting for the pressure test.",
        ),
        context("og:note:plumbing:pressure-test"),
    )

    assert assigned.task.assigned_to == "usr_kofi123"
    assert prioritized.task.priority is TaskPriority.HIGH
    assert noted.task.notes == ["Waiting for the pressure test."]
    assert {event.action for event in task_store.repository(ActivityEvent).list(PROJECT_ID)} == {
        "task.assigned",
        "task.priority_changed",
        "task.note_added",
    }


def test_unresolved_entity_and_viewer_role_fail_before_mutation() -> None:
    task_store = store()
    service = ConversationTaskService(TaskService(task_store), task_store)
    unresolved = ConversationTaskCommand(
        operation=TaskOperation.CHANGE_STATUS,
        task=resolution(status=EntityResolutionStatus.AMBIGUOUS),
        target_status=TaskStatus.BLOCKED,
    )

    with pytest.raises(ValueError, match="resolved task"):
        service.execute(access(), unresolved, context("og:ambiguous"))
    with pytest.raises(RoleRequiredError):
        service.execute(
            access(MemberRole.VIEWER),
            ConversationTaskCommand(
                operation=TaskOperation.CHANGE_STATUS,
                task=resolution(),
                target_status=TaskStatus.BLOCKED,
            ),
            context("og:viewer-status"),
        )

    assert task_store.repository(Task).require(PROJECT_ID, "tsk_plumbing123").version == 0
    assert task_store.repository(ActivityEvent).list(PROJECT_ID) == ()


def test_create_task_uses_existing_manage_only_service_and_is_idempotent() -> None:
    task_store = store()
    service = ConversationTaskService(TaskService(task_store), task_store)
    command = ConversationTaskCommand(
        operation=TaskOperation.CREATE,
        title="Scaffolding",
        priority=TaskPriority.MEDIUM,
        planned_start=NOW,
    )

    first = service.execute(access(MemberRole.ADMIN), command, context("og:create:scaffolding"))
    replay = service.execute(access(MemberRole.ADMIN), command, context("og:create:scaffolding"))

    assert first.task.title == "Scaffolding"
    assert first.task.planned_start == NOW
    assert first.reply == "Done. I created Scaffolding."
    assert replay.duplicate is True
    assert (
        len(
            [
                task
                for task in task_store.repository(Task).list(PROJECT_ID)
                if task.title == "Scaffolding"
            ]
        )
        == 1
    )


def test_stale_conversational_task_command_surfaces_conflict_without_overwrite() -> None:
    task_store = store()
    service = ConversationTaskService(TaskService(task_store), task_store)
    current = task_store.repository(Task).require(PROJECT_ID, "tsk_plumbing123")
    service.execute(
        access(),
        ConversationTaskCommand(
            operation=TaskOperation.ADD_NOTE,
            task=resolution(),
            note="Fresh change",
            expected_version=current.version,
        ),
        context("og:fresh-note"),
    )

    with pytest.raises(VersionConflictError, match="changed after OG loaded"):
        service.execute(
            access(),
            ConversationTaskCommand(
                operation=TaskOperation.CHANGE_PRIORITY,
                task=resolution(),
                priority=TaskPriority.HIGH,
                expected_version=current.version,
            ),
            context("og:stale-priority"),
        )

    persisted = task_store.repository(Task).require(PROJECT_ID, "tsk_plumbing123")
    assert persisted.notes == ["Fresh change"]
    assert persisted.priority is TaskPriority.MEDIUM
