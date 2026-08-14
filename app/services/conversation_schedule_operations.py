"""Dependency-aware conversational schedule proposals and mutations."""

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import hmac
import json

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
    ScheduleProposalToken,
    ScheduleTaskVersion,
)
from app.domain.enums import ActorType, ApprovalActionType, ApprovalStatus
from app.domain.models import Approval, Task
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.interfaces import VersionConflictError
from app.repositories.tasks import TaskRepository
from app.services.activity import ActivityService
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.schedule_impact import calculate_impact


@dataclass(frozen=True, slots=True)
class ScheduleProposal:
    policy: MutationPolicyClass
    affected_task_ids: tuple[str, ...]
    token: ScheduleProposalToken
    reply: str


@dataclass(frozen=True, slots=True)
class ScheduleChangeResult:
    tasks: tuple[Task, ...]
    reply: str
    duplicate: bool = False


class ConversationScheduleService:
    def __init__(
        self,
        store: RepositoryStore,
        policies: MutationPolicyService,
        *,
        proposal_signing_key: bytes,
    ) -> None:
        if len(proposal_signing_key) < 32:
            raise ValueError("schedule proposal signing key must be at least 32 bytes")
        self._store = store
        self._policies = policies
        self._activities = ActivityService(store)
        self._proposal_signing_key = proposal_signing_key

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
        tasks_by_id = {task.id: task for task in tasks}
        versions = tuple(
            ScheduleTaskVersion(task_id=task_id, version=tasks_by_id[task_id].version)
            for task_id in affected
        )
        token = ScheduleProposalToken(
            project_id=access.project_id,
            actor_id=access.actor.user_id,
            target_task_id=task_id,
            planned_start=command.planned_start,
            planned_end=command.planned_end,
            affected_versions=versions,
            signature="0" * 64,
        )
        token = token.model_copy(update={"signature": self._sign(token)})
        return ScheduleProposal(
            policy,
            affected,
            token,
            f"That shifts {current.title}{impact}. Update the schedule?",
        )

    def execute(
        self, access: ProjectAccessContext, command: ScheduleChangeCommand, context: MutationContext
    ) -> ScheduleChangeResult:
        ensure_project_scope(access, command.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if not command.confirmed:
            proposal = self.propose(access, command)
            return ScheduleChangeResult((), proposal.reply)
        ensure_project_scope(access, context.project_id)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("schedule change requires the authorized user actor")
        return self._execute_confirmed(access, command, context, allow_major=False)

    def execute_approved(
        self,
        access: ProjectAccessContext,
        command: ScheduleChangeCommand,
        context: MutationContext,
        approval: Approval,
    ) -> ScheduleChangeResult:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        if context.actor_type is not ActorType.SYSTEM:
            raise PermissionError("approved schedule continuation requires the system actor")
        if (
            approval.project_id != access.project_id
            or approval.action_type is not ApprovalActionType.SCHEDULE_CHANGE
            or approval.status is not ApprovalStatus.APPROVED
        ):
            raise PermissionError("schedule change does not have a valid approved decision")
        return self._execute_confirmed(access, command, context, allow_major=True)

    def _execute_confirmed(
        self,
        access: ProjectAccessContext,
        command: ScheduleChangeCommand,
        context: MutationContext,
        *,
        allow_major: bool,
    ) -> ScheduleChangeResult:
        task_id = _task_id(command)
        token = self._confirmed_token(access, command, task_id, allow_major=allow_major)
        affected = tuple(item.task_id for item in token.affected_versions)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="schedule.updated",
                entity_type="task",
                entity_id=task_id,
                summary="Updated task schedule with dependency impact",
                metadata={
                    "affected_task_ids": list(affected),
                    "planned_start": command.planned_start.isoformat(),
                    "planned_end": command.planned_end.isoformat(),
                    "proposal_versions": {
                        item.task_id: item.version for item in token.affected_versions
                    },
                },
            ),
            lambda session: _apply(session, access, command, token, context),
            replay=lambda session, activity: _replay_tasks(session, access, activity.metadata),
        )
        if result.value is None:
            raise RuntimeError("schedule replay did not resolve persisted tasks")
        return ScheduleChangeResult(
            tuple(result.value), "Done. I updated the schedule.", result.duplicate
        )

    def _sign(self, token: ScheduleProposalToken) -> str:
        payload = json.dumps(
            token.model_dump(mode="json", exclude={"signature"}),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hmac.new(self._proposal_signing_key, payload, sha256).hexdigest()

    def _confirmed_token(
        self,
        access: ProjectAccessContext,
        command: ScheduleChangeCommand,
        task_id: str,
        *,
        allow_major: bool = False,
    ) -> ScheduleProposalToken:
        token = command.proposal
        if token is None:
            raise ValueError("confirmed schedule changes require the reviewed proposal")
        if not hmac.compare_digest(token.signature, self._sign(token)):
            raise PermissionError("schedule proposal signature is invalid")
        if (
            token.project_id != access.project_id
            or token.actor_id != access.actor.user_id
            or token.target_task_id != task_id
            or token.planned_start != command.planned_start
            or token.planned_end != command.planned_end
        ):
            raise VersionConflictError("confirmed schedule command does not match its proposal")
        if len(token.affected_versions) > 3 and not allow_major:
            raise PermissionError("major schedule changes require the approval workflow")
        return token


def _apply(
    session: RepositorySession,
    access: ProjectAccessContext,
    command: ScheduleChangeCommand,
    token: ScheduleProposalToken,
    context: MutationContext,
) -> tuple[Task, ...]:
    repository = TaskRepository.for_session(session, access)
    affected = tuple(item.task_id for item in token.affected_versions)
    all_tasks = tuple(repository.list(command.project_id))
    persisted_ids = {task.id for task in all_tasks}
    if not set(affected).issubset(persisted_ids):
        raise VersionConflictError("schedule proposal is stale; an affected task no longer exists")
    current_impact = calculate_impact(all_tasks, [token.target_task_id])
    current_affected = (
        token.target_task_id,
        *sorted(item for item in current_impact if item != token.target_task_id),
    )
    if current_affected != affected:
        raise VersionConflictError("schedule proposal is stale; review the dependency impact")
    tasks = {task_id: repository.require(command.project_id, task_id) for task_id in affected}
    expected = {item.task_id: item.version for item in token.affected_versions}
    actual = {task_id: task.version for task_id, task in tasks.items()}
    if not expected or expected != actual:
        raise VersionConflictError("schedule proposal is stale; review the current schedule")
    current = tasks[_task_id(command)]
    delta = command.planned_start - (current.planned_start or command.planned_start)
    saved = []
    for task_id in affected:
        task = tasks[task_id]
        updates: dict[str, object] = {"updated_at": context.occurred_at}
        if task.id == current.id:
            updates.update(planned_start=command.planned_start, planned_end=command.planned_end)
        else:
            updates.update(
                planned_start=task.planned_start + delta if task.planned_start else None,
                planned_end=task.planned_end + delta if task.planned_end else None,
            )
        saved.append(
            repository.save(task.model_copy(update=updates), expected_version=expected[task_id])
        )
    return tuple(saved)


def _replay_tasks(
    session: RepositorySession,
    access: ProjectAccessContext,
    metadata: dict[str, object],
) -> tuple[Task, ...]:
    affected = metadata.get("affected_task_ids")
    if not isinstance(affected, list) or not all(isinstance(item, str) for item in affected):
        raise RuntimeError("schedule activity is missing its affected task identities")
    repository = TaskRepository.for_session(session, access)
    return tuple(repository.require(access.project_id, item) for item in affected)


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
