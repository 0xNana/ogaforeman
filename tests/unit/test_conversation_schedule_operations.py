from datetime import UTC, datetime, timedelta

import pytest

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
from app.repositories.activity import ActivityIdempotencyConflict
from app.repositories.interfaces import VersionConflictError
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_schedule_operations import ConversationScheduleService

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
PID = "prj_schedule123"
SIGNING_KEY = b"schedule-proposal-test-signing-key-32-bytes"


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


def schedule_service(data: InMemoryRepositoryStore) -> ConversationScheduleService:
    return ConversationScheduleService(
        data, MutationPolicyService(), proposal_signing_key=SIGNING_KEY
    )


def test_schedule_proposal_calculates_dependency_impact_without_mutation() -> None:
    data = store()
    service = schedule_service(data)
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
    service = schedule_service(data)
    proposed_command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    proposal = service.propose(access(), proposed_command)
    command = proposed_command.model_copy(
        update={"confirmed": True, "proposal": proposal.token}
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
    service = schedule_service(data)
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


def test_confirmed_schedule_change_rejects_state_changed_after_proposal() -> None:
    data = store()
    service = schedule_service(data)
    proposed_command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    proposal = service.propose(access(), proposed_command)
    repository = data.repository(Task)
    painting = repository.require(PID, "tsk_painting123")
    repository.save(
        painting.model_copy(update={"planned_end": NOW + timedelta(days=5)}),
        expected_version=painting.version,
    )

    with pytest.raises(VersionConflictError, match="schedule proposal is stale"):
        service.execute(
            access(),
            proposed_command.model_copy(
                update={"confirmed": True, "proposal": proposal.token}
            ),
            context("og:schedule:stale"),
        )

    assert data.repository(ActivityEvent).list(PID) == ()


def test_confirmation_rejects_target_swapped_after_proposal() -> None:
    data = store()
    service = schedule_service(data)
    command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    proposal = service.propose(access(), command)
    switched = command.model_copy(
        update={
            "task": task_ref().model_copy(
                update={"entity_id": "tsk_painting123", "display_name": "Painting preparation"}
            ),
            "confirmed": True,
            "proposal": proposal.token,
        }
    )

    with pytest.raises(VersionConflictError, match="does not match its proposal"):
        service.execute(access(), switched, context("og:schedule:switched"))


def test_replay_survives_later_dependency_graph_change() -> None:
    data = store()
    service = schedule_service(data)
    command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    proposal = service.propose(access(), command)
    confirmed = command.model_copy(update={"confirmed": True, "proposal": proposal.token})
    service.execute(access(), confirmed, context("og:schedule:stable-replay"))
    data.repository(Task).create(
        Task(
            id="tsk_cleanup123",
            project_id=PID,
            title="Cleanup",
            status=TaskStatus.PLANNED,
            dependency_ids=["tsk_plastering123"],
        )
    )

    replay = service.execute(access(), confirmed, context("og:schedule:stable-replay"))

    assert replay.duplicate is True
    assert {item.id for item in replay.tasks} == {"tsk_plastering123", "tsk_painting123"}


def test_same_idempotency_key_rejects_a_different_schedule_payload() -> None:
    data = store()
    service = schedule_service(data)
    first = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    first_proposal = service.propose(access(), first)
    service.execute(
        access(),
        first.model_copy(update={"confirmed": True, "proposal": first_proposal.token}),
        context("og:schedule:reused-key"),
    )
    different = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=5),
        planned_end=NOW + timedelta(days=6),
    )
    different_proposal = service.propose(access(), different)

    with pytest.raises(ActivityIdempotencyConflict):
        service.execute(
            access(),
            different.model_copy(
                update={"confirmed": True, "proposal": different_proposal.token}
            ),
            context("og:schedule:reused-key"),
        )


def test_confirmed_schedule_rejects_a_forged_proposal_token() -> None:
    data = store()
    service = schedule_service(data)
    command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    proposal = service.propose(access(), command)
    forged = proposal.token.model_copy(update={"signature": "0" * 64})

    with pytest.raises(PermissionError, match="signature is invalid"):
        service.execute(
            access(),
            command.model_copy(update={"confirmed": True, "proposal": forged}),
            context("og:schedule:forged"),
        )

    assert data.repository(ActivityEvent).list(PID) == ()


def test_confirmed_schedule_reports_deleted_target_as_stale() -> None:
    data = store()
    repository = data.repository(Task)
    painting = repository.require(PID, "tsk_painting123")
    repository.delete(PID, painting.id, expected_version=painting.version)
    service = schedule_service(data)
    command = ScheduleChangeCommand(
        project_id=PID,
        task=task_ref(),
        planned_start=NOW + timedelta(days=3),
        planned_end=NOW + timedelta(days=4),
    )
    proposal = service.propose(access(), command)
    plastering = repository.require(PID, "tsk_plastering123")
    repository.delete(PID, plastering.id, expected_version=plastering.version)

    with pytest.raises(VersionConflictError, match="no longer exists"):
        service.execute(
            access(),
            command.model_copy(update={"confirmed": True, "proposal": proposal.token}),
            context("og:schedule:deleted"),
        )

    assert data.repository(ActivityEvent).list(PID) == ()
