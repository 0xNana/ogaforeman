"""Dependency-aware conversational schedule proposals and mutations."""

from dataclasses import dataclass
from datetime import timedelta

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.conversation import (
    EntityKind,
    EntityResolutionStatus,
    MutationKind,
    MutationPolicyClass,
    MutationPolicyRequest,
    ScheduleChangeCommand,
)
from app.domain.enums import ActorType
from app.domain.models import Task
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.tasks import TaskRepository
from app.services.activity import ActivityService
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.schedule_impact import calculate_impact


@dataclass(frozen=True, slots=True)
class ScheduleProposal:
    policy: MutationPolicyClass
    affected_task_ids: tuple[str, ...]
    reply: str


@dataclass(frozen=True, slots=True)
class ScheduleChangeResult:
    tasks: tuple[Task, ...]
    reply: str
    duplicate: bool = False


class ConversationScheduleService:
    def __init__(self, store: RepositoryStore, policies: MutationPolicyService) -> None:
        self._store = store
        self._policies = policies
        self._activities = ActivityService(store)

    def propose(
        self, access: ProjectAccessContext, command: ScheduleChangeCommand
    ) -> ScheduleProposal:
        ensure_project_scope(access, command.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        task_id = _task_id(command)
        tasks = tuple(TaskRepository(self._store).list(access))
        current = next(task for task in tasks if task.id == task_id)
        impacted_ids = calculate_impact(tasks, [task_id])
        affected = (task_id, *sorted(item for item in impacted_ids if item != task_id))
        kind = (
            MutationKind.MAJOR_SCHEDULE_CHANGE if len(affected) > 3 else MutationKind.SCHEDULE_DATES
        )
        policy = self._policies.classify(
            access,
            MutationPolicyRequest(
                project_id=command.project_id,
                kind=kind,
                dependent_entity_count=max(0, len(affected) - 1),
            ),
        ).policy
        delta = command.planned_start - (current.planned_start or command.planned_start)
        downstream = [
            task.title for task in tasks if task.id in impacted_ids and task.id != task_id
        ]
        impact = f" and moves {', '.join(downstream)} by {_days(delta)} days" if downstream else ""
        return ScheduleProposal(
            policy, affected, f"That shifts {current.title}{impact}. Update the schedule?"
        )

    def execute(
        self, access: ProjectAccessContext, command: ScheduleChangeCommand, context: MutationContext
    ) -> ScheduleChangeResult:
        proposal = self.propose(access, command)
        if proposal.policy is not MutationPolicyClass.CONFIRM_FIRST or not command.confirmed:
            return ScheduleChangeResult((), proposal.reply)
        ensure_project_scope(access, context.project_id)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("schedule change requires the authorized user actor")
        task_id = _task_id(command)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="schedule.updated",
                entity_type="task",
                entity_id=task_id,
                summary="Updated task schedule with dependency impact",
                metadata={"affected_task_ids": list(proposal.affected_task_ids)},
            ),
            lambda session: _apply(session, access, command, proposal.affected_task_ids, context),
            replay=lambda session, activity: tuple(
                TaskRepository.for_session(session, access).require(activity.project_id, item)
                for item in proposal.affected_task_ids
            ),
        )
        if result.value is None:
            raise RuntimeError("schedule replay did not resolve persisted tasks")
        return ScheduleChangeResult(
            tuple(result.value), "Done. I updated the schedule.", result.duplicate
        )


def _apply(
    session: RepositorySession,
    access: ProjectAccessContext,
    command: ScheduleChangeCommand,
    affected: tuple[str, ...],
    context: MutationContext,
) -> tuple[Task, ...]:
    repository = TaskRepository.for_session(session, access)
    current = repository.require(command.project_id, _task_id(command))
    delta = command.planned_start - (current.planned_start or command.planned_start)
    saved = []
    for task_id in affected:
        task = repository.require(command.project_id, task_id)
        version = repository.version_of(command.project_id, task_id)
        if version is None:
            raise RuntimeError("scheduled task has no persisted version")
        updates: dict[str, object] = {"updated_at": context.occurred_at}
        if task.id == current.id:
            updates.update(planned_start=command.planned_start, planned_end=command.planned_end)
        else:
            updates.update(
                planned_start=task.planned_start + delta if task.planned_start else None,
                planned_end=task.planned_end + delta if task.planned_end else None,
            )
        saved.append(repository.save(task.model_copy(update=updates), expected_version=version))
    return tuple(saved)


def _task_id(command: ScheduleChangeCommand) -> str:
    ref = command.task
    if (
        ref.kind is not EntityKind.TASK
        or ref.status is not EntityResolutionStatus.RESOLVED
        or not ref.can_mutate
        or ref.entity_id is None
    ):
        raise ValueError("a resolved task is required")
    return ref.entity_id


def _days(delta: timedelta) -> int:
    return round(delta.total_seconds() / 86400)


__all__ = ["ConversationScheduleService", "ScheduleChangeResult", "ScheduleProposal"]
