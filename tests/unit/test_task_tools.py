from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.activity import MutationContext
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectForbiddenError,
    RoleRequiredError,
)
from app.domain.enums import ActorType, MemberRole, TaskStatus
from app.domain.models import ActivityEvent, Task
from app.repositories.interfaces import VersionConflictError
from app.repositories.memory import InMemoryRepositoryStore
from app.services.tasks import (
    TaskBlockedCompletionError,
    TaskDependencyIncompleteError,
    TaskEvidenceRejectedError,
    TaskService,
    UpdateTaskCommand,
)
from app.tools.tasks import update_task_progress


NOW = datetime(2026, 8, 7, 13, 0, tzinfo=UTC)


def make_access(
    *,
    project_id: str = "prj_ridge",
    role: MemberRole = MemberRole.FOREMAN,
) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman", subject="firebase-foreman"),
        project_id=project_id,
        role=role,
    )


def make_context(**updates: object) -> MutationContext:
    values: dict[str, object] = {
        "project_id": "prj_ridge",
        "actor_type": ActorType.AGENT,
        "actor_id": "agt_site_report",
        "source_event_id": "evt_update001",
        "agent_run_id": "run_update001",
        "idempotency_key": "task-update:evt_update001:tsk_blockwork",
        "occurred_at": NOW,
    }
    values.update(updates)
    return MutationContext(**values)


def make_command(**updates: object) -> UpdateTaskCommand:
    values: dict[str, object] = {
        "project_id": "prj_ridge",
        "task_id": "tsk_blockwork",
        "expected_version": 0,
        "completion_percentage": Decimal("60"),
        "evidence": "Foreman reported blockwork progress.",
        "occurred_at": NOW,
    }
    values.update(updates)
    return UpdateTaskCommand(**values)


def make_store(task: Task | None = None) -> InMemoryRepositoryStore:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        task
        or Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("40"),
        )
    )
    return store


def test_valid_typed_tool_updates_existing_task_and_emits_one_activity() -> None:
    store = make_store()
    service = TaskService(store)

    result = update_task_progress(
        make_command(),
        service=service,
        access=make_access(),
        context=make_context(),
    )

    assert not isinstance(result, dict)
    assert result.task.id == "tsk_blockwork"
    assert result.task.completion_percent == 60
    assert result.task.version == 1
    assert result.activity.action == "task.updated"
    assert result.activity.source_event_id == "evt_update001"
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_negated_update_does_not_mutate_or_emit_activity() -> None:
    store = make_store()

    with pytest.raises(TaskEvidenceRejectedError, match="negated"):
        TaskService(store).update_task(
            make_access(),
            make_command(is_negated=True),
            make_context(),
        )

    assert store.repository(Task).require("prj_ridge", "tsk_blockwork").version == 0
    assert store.repository(ActivityEvent).list("prj_ridge") == ()


def test_duplicate_update_replays_one_task_version_and_activity() -> None:
    store = make_store()
    service = TaskService(store)

    first = service.update_task(make_access(), make_command(), make_context())
    duplicate = service.update_task(make_access(), make_command(), make_context())

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert duplicate.task.version == 1
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_stale_version_conflict_rolls_back_activity() -> None:
    store = make_store()

    with pytest.raises(VersionConflictError):
        TaskService(store).update_task(
            make_access(),
            make_command(expected_version=3),
            make_context(),
        )

    assert store.repository(Task).require("prj_ridge", "tsk_blockwork").version == 0
    assert store.repository(ActivityEvent).list("prj_ridge") == ()


def test_forbidden_project_and_viewer_role_fail_at_service_and_repository_boundary() -> None:
    store = make_store()
    service = TaskService(store)

    with pytest.raises(ProjectForbiddenError):
        service.update_task(
            make_access(project_id="prj_other"),
            make_command(),
            make_context(),
        )

    with pytest.raises(RoleRequiredError):
        service.update_task(
            make_access(role=MemberRole.VIEWER),
            make_command(),
            make_context(),
        )


def test_blocked_or_dependency_blocked_task_cannot_complete() -> None:
    blocked_store = make_store(
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="First-floor blockwork",
            status=TaskStatus.BLOCKED,
            completion_percent=Decimal("80"),
        )
    )
    completion = make_command(completion_percentage=Decimal("100"))

    with pytest.raises(TaskBlockedCompletionError):
        TaskService(blocked_store).update_task(make_access(), completion, make_context())

    dependency_store = InMemoryRepositoryStore()
    dependency_store.repository(Task).create(
        Task(
            id="tsk_foundation",
            project_id="prj_ridge",
            title="Foundation",
            status=TaskStatus.PLANNED,
        )
    )
    dependency_store.repository(Task).create(
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
            dependency_ids=["tsk_foundation"],
        )
    )

    with pytest.raises(TaskDependencyIncompleteError, match="tsk_foundation"):
        TaskService(dependency_store).update_task(make_access(), completion, make_context())

    assert dependency_store.repository(ActivityEvent).list("prj_ridge") == ()
