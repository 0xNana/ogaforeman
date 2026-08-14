from datetime import UTC, datetime, timedelta

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    MutationPolicyClass,
    ScheduleChangeCommand,
)
from app.domain.enums import ActorType, MemberRole, TaskStatus
from app.domain.models import ActivityEvent, Task
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_schedule_operations import ConversationScheduleService

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
PID = "prj_schedule123"


def access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager"),
        project_id=PID,
        role=MemberRole.MANAGER,
    )


def context(key: str) -> MutationContext:
    return MutationContext(
        project_id=PID,
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        idempotency_key=key,
        occurred_at=NOW,
    )


def task_ref() -> EntityResolution:
    return EntityResolution(
        kind=EntityKind.TASK,
        reference="plastering",
        status=EntityResolutionStatus.RESOLVED,
        entity_id="tsk_plastering123",
        display_name="Plastering",
        match_method="exact",
        can_mutate=True,
    )


def store() -> InMemoryRepositoryStore:
    data = InMemoryRepositoryStore()
    data.repository(Task).create(
        Task(
            id="tsk_plastering123",
            project_id=PID,
            title="Plastering",
            status=TaskStatus.PLANNED,
            planned_start=NOW + timedelta(days=1),
            planned_end=NOW + timedelta(days=2),
        )
    )
    data.repository(Task).create(
        Task(
            id="tsk_painting123",
            project_id=PID,
            title="Painting preparation",
            status=TaskStatus.PLANNED,
            planned_start=NOW + timedelta(days=2),
            planned_end=NOW + timedelta(days=3),
            dependency_ids=["tsk_plastering123"],
        )
    )
    return data


def test_schedule_proposal_calculates_dependency_impact_without_mutation() -> None:
    data = store()
    service = ConversationScheduleService(data, MutationPolicyService())
    proposal = service.propose(
        access(),
        ScheduleChangeCommand(
            project_id=PID,
            task=task_ref(),
            planned_start=NOW + timedelta(days=3),
            planned_end=NOW + timedelta(days=4),
        ),
    )
    assert proposal.policy is MutationPolicyClass.CONFIRM_FIRST
    assert proposal.affected_task_ids == ("tsk_plastering123", "tsk_painting123")
    assert "moves Painting preparation by 2 days" in proposal.reply
    assert data.repository(ActivityEvent).list(PID) == ()


def test_confirmed_schedule_change_shifts_dependencies_atomically_and_replays() -> None:
    data = store()
    service = ConversationScheduleService(data, MutationPolicyService())
    command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
        confirmed=True,
    )
    first = service.execute(access(), command, context("og:schedule:plastering"))
    replay = service.execute(access(), command, context("og:schedule:plastering"))
    assert first.tasks[0].planned_start == NOW + timedelta(days=3)
    assert {task.id: task.planned_start for task in first.tasks}[
        "tsk_painting123"
    ] == NOW + timedelta(days=4)
    assert replay.duplicate is True
    assert len(data.repository(ActivityEvent).list(PID)) == 1


def test_unconfirmed_schedule_change_never_executes() -> None:
    data = store()
    service = ConversationScheduleService(data, MutationPolicyService())
    result = service.execute(
        access(),
        ScheduleChangeCommand(
            project_id=PID,
            task=task_ref(),
            planned_start=NOW + timedelta(days=3),
            planned_end=NOW + timedelta(days=4),
        ),
        context("og:schedule:no-confirm"),
    )
    assert result.tasks == ()
    assert data.repository(Task).require(PID, "tsk_plastering123").planned_start == NOW + timedelta(
        days=1
    )
