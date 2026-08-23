"""Deterministic, repository-backed task mutation commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Self

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import (
    ActorType,
    IssueType,
    MemberStatus,
    Severity,
    TaskPriority,
    TaskSource,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    CanonicalId,
    Issue,
    MaterialRequest,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.domain.policies import InvalidTransitionError, ensure_task_transition
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.tasks import TaskRepository
from app.services.activity import ActivityService


class TaskMutationError(ValueError):
    code = "VALIDATION_FAILED"


class TaskEvidenceRejectedError(TaskMutationError):
    """Evidence polarity is not safe for a state mutation."""


class TaskStateError(TaskMutationError):
    code = "INVALID_STATE_TRANSITION"


class TaskBlockedCompletionError(TaskStateError):
    """A blocked task cannot be completed by this command."""


class TaskDependencyIncompleteError(TaskStateError):
    """One or more task dependencies are not complete."""


class TaskApprovalRequiredError(TaskMutationError):
    code = "APPROVAL_REQUIRED"


class CreateTaskCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: CanonicalId | None = None
    trade: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=500)
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    is_milestone: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        return self


class CreateBlockerFollowUpCommand(BaseModel):
    """Create one source-linked operational task for a persisted blocker."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    blocked_task_id: CanonicalId
    source_issue_id: CanonicalId
    source_site_update_id: CanonicalId
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateDeliveryFollowUpCommand(BaseModel):
    """Create one source-linked task for a delayed approved delivery."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    material_request_id: CanonicalId
    source_issue_id: CanonicalId
    source_event_id: CanonicalId
    affected_task_ids: tuple[CanonicalId, ...] = Field(default=(), max_length=100)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class UpdateTaskCommand(BaseModel):
    """Typed task update produced by a workflow or explicit user action."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    project_id: CanonicalId
    task_id: CanonicalId
    expected_version: int = Field(ge=0)
    completion_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        validation_alias=AliasChoices("completion_percent", "completion_percentage"),
    )
    target_status: TaskStatus | None = Field(
        default=None,
        validation_alias=AliasChoices("target_status", "status"),
    )
    evidence: str | None = Field(default=None, min_length=1, max_length=5_000)
    negated: bool = Field(default=False, validation_alias=AliasChoices("negated", "is_negated"))
    ambiguous: bool = Field(
        default=False,
        validation_alias=AliasChoices("ambiguous", "is_ambiguous"),
    )
    human_correction: bool = False
    reconciled_completion: bool = False
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if self.completion_percent is None and self.target_status is None:
            raise ValueError("task update requires completion_percent or target_status")
        if self.requests_completion and not self.evidence:
            raise ValueError("task completion requires explicit evidence")
        if self.human_correction and self.target_status is not TaskStatus.IN_PROGRESS:
            raise ValueError("human_correction is only valid when reopening a task")
        if self.reconciled_completion and not self.requests_completion:
            raise ValueError("reconciled_completion is only valid for task completion")
        return self

    @property
    def requests_completion(self) -> bool:
        return self.target_status is TaskStatus.COMPLETED or self.completion_percent == Decimal(
            "100"
        )


TaskUpdateCommand = UpdateTaskCommand


class UpdateTaskDetailsCommand(BaseModel):
    """Routine non-status task fields supported by typed user operations."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    task_id: CanonicalId
    expected_version: int = Field(ge=0)
    assigned_to: CanonicalId | None = None
    priority: TaskPriority | None = None
    planned_end: AwareDatetime | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def require_one_change(self) -> Self:
        supplied = sum(
            value is not None
            for value in (self.assigned_to, self.priority, self.planned_end, self.note)
        )
        if supplied != 1:
            raise ValueError("task detail update requires exactly one field")
        return self


@dataclass(frozen=True, slots=True)
class TaskChange:
    task: Task
    activity: ActivityEvent
    duplicate: bool = False

    @property
    def replayed(self) -> bool:
        return self.duplicate


class TaskService:
    """Apply task updates with authorization, policy, idempotency, and audit."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._activities = ActivityService(store)

    def create_task(
        self,
        access: ProjectAccessContext,
        command: CreateTaskCommand,
        context: MutationContext,
    ) -> TaskChange:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.MANAGE)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("task setup requires the authorized user actor")
        if command.assigned_to is not None:
            membership = self._store.repository(ProjectMember).get(
                command.project_id, command.assigned_to
            )
            if membership is None or membership.status is not MemberStatus.ACTIVE:
                raise PermissionError("task assignee must be an active project member")
        task_id = _created_task_id(context)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="task.created",
                entity_type="task",
                entity_id=task_id,
                summary=f"Created task {command.title}.",
                metadata={"priority": command.priority.value},
            ),
            lambda session: session.repository(Task).create(
                Task(
                    id=task_id,
                    project_id=command.project_id,
                    title=command.title,
                    description=command.description,
                    status=TaskStatus.PLANNED,
                    priority=command.priority,
                    assigned_to=command.assigned_to,
                    trade=command.trade,
                    location=command.location,
                    planned_start=command.planned_start,
                    planned_end=command.planned_end,
                    is_milestone=command.is_milestone,
                    source=TaskSource.MANUAL,
                    created_at=context.occurred_at,
                    updated_at=context.occurred_at,
                )
            ),
            replay=lambda session, activity: session.repository(Task).require(
                command.project_id, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("task creation replay did not resolve persisted state")
        return TaskChange(
            task=result.value,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    def create_blocker_follow_up(
        self,
        access: ProjectAccessContext,
        command: CreateBlockerFollowUpCommand,
        context: MutationContext,
    ) -> TaskChange:
        self._authorize_follow_up(access, command, context)
        task_id = _created_task_id(context)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="task.follow_up_created",
                entity_type="task",
                entity_id=task_id,
                summary="Created a blocker follow-up task.",
                metadata={
                    "blocked_task_id": command.blocked_task_id,
                    "source_issue_id": command.source_issue_id,
                    "source_site_update_id": command.source_site_update_id,
                },
            ),
            lambda session: self._create_blocker_follow_up(
                session,
                access,
                command,
                task_id,
            ),
            replay=lambda session, activity: TaskRepository.for_session(session, access).require(
                command.project_id, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("follow-up task replay did not resolve persisted state")
        return TaskChange(
            task=result.value,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    def create_delivery_follow_up(
        self,
        access: ProjectAccessContext,
        command: CreateDeliveryFollowUpCommand,
        context: MutationContext,
    ) -> TaskChange:
        self._authorize_delivery_follow_up(access, command, context)
        task_id = _created_task_id(context)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="task.delivery_follow_up_created",
                entity_type="task",
                entity_id=task_id,
                summary="Created a delayed-delivery follow-up task.",
                metadata={
                    "material_request_id": command.material_request_id,
                    "source_issue_id": command.source_issue_id,
                    "affected_task_ids": list(command.affected_task_ids),
                },
            ),
            lambda session: self._create_delivery_follow_up(
                session,
                access,
                command,
                task_id,
            ),
            replay=lambda session, activity: TaskRepository.for_session(session, access).require(
                command.project_id, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("delivery follow-up replay did not resolve persisted state")
        return TaskChange(result.value, result.activity, result.duplicate)

    def update_task(
        self,
        access: ProjectAccessContext,
        command: UpdateTaskCommand,
        context: MutationContext,
    ) -> TaskChange:
        self._authorize(access, command, context)
        self._validate_evidence(command)
        spec = _activity_spec(command)

        result = self._activities.mutate(
            context,
            spec,
            lambda session: self._apply_update(session, access, command, context),
            replay=lambda session, activity: TaskRepository.for_session(session, access).require(
                activity.project_id, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("task replay did not resolve its persisted entity")
        return TaskChange(
            task=result.value,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    def complete_task(
        self,
        access: ProjectAccessContext,
        command: UpdateTaskCommand,
        context: MutationContext,
    ) -> TaskChange:
        if not command.evidence:
            raise TaskEvidenceRejectedError("task completion requires explicit evidence")
        if command.target_status is not TaskStatus.COMPLETED:
            command = UpdateTaskCommand.model_validate(
                {**command.model_dump(), "target_status": TaskStatus.COMPLETED}
            )
        return self.update_task(access, command, context)

    def update_task_details(
        self,
        access: ProjectAccessContext,
        command: UpdateTaskDetailsCommand,
        context: MutationContext,
    ) -> TaskChange:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("task detail update requires the authorized user actor")
        spec = _details_activity_spec(command)
        result = self._activities.mutate(
            context,
            spec,
            lambda session: self._apply_details(session, access, command),
            replay=lambda session, activity: TaskRepository.for_session(session, access).require(
                activity.project_id, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("task detail replay did not resolve its persisted entity")
        return TaskChange(result.value, result.activity, result.duplicate)

    @staticmethod
    def _apply_details(
        session: RepositorySession,
        access: ProjectAccessContext,
        command: UpdateTaskDetailsCommand,
    ) -> Task:
        repository = TaskRepository.for_session(session, access)
        current = repository.require(command.project_id, command.task_id)
        updates: dict[str, object] = {"updated_at": command.occurred_at}
        if command.assigned_to is not None:
            membership = session.repository(ProjectMember).get(
                command.project_id, command.assigned_to
            )
            if membership is None or membership.status is not MemberStatus.ACTIVE:
                raise PermissionError("task assignee must be an active project member")
            updates["assigned_to"] = command.assigned_to
        elif command.priority is not None:
            updates["priority"] = command.priority
        elif command.planned_end is not None:
            if current.planned_start and command.planned_end < current.planned_start:
                raise TaskMutationError("planned_end cannot be before planned_start")
            updates["planned_end"] = command.planned_end
        elif command.note is not None:
            if len(current.notes) >= 100:
                raise TaskMutationError("task note limit reached")
            updates["notes"] = [*current.notes, command.note]
        return repository.save(
            current.model_copy(update=updates),
            expected_version=command.expected_version,
        )

    @staticmethod
    def _authorize_follow_up(
        access: ProjectAccessContext,
        command: CreateBlockerFollowUpCommand,
        context: MutationContext,
    ) -> None:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")

    @staticmethod
    def _authorize_delivery_follow_up(
        access: ProjectAccessContext,
        command: CreateDeliveryFollowUpCommand,
        context: MutationContext,
    ) -> None:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")

    @staticmethod
    def _create_delivery_follow_up(
        session: RepositorySession,
        access: ProjectAccessContext,
        command: CreateDeliveryFollowUpCommand,
        task_id: str,
    ) -> Task:
        tasks = TaskRepository.for_session(session, access)
        request = session.repository(MaterialRequest).require(
            command.project_id, command.material_request_id
        )
        issue = session.repository(Issue).require(command.project_id, command.source_issue_id)
        if issue.type is not IssueType.DELAY_RISK:
            raise TaskStateError("delivery follow-up source issue must be a delay risk")
        if command.source_event_id not in issue.evidence_refs:
            raise TaskStateError("delivery follow-up issue must reference the delivery event")
        affected = [tasks.require(command.project_id, task_id) for task_id in command.affected_task_ids]
        if set(command.affected_task_ids) - set(issue.task_ids):
            raise TaskStateError("delivery follow-up tasks must be referenced by the risk issue")
        primary = affected[0] if affected else None
        return tasks.create(
            Task(
                id=task_id,
                project_id=command.project_id,
                title=f"Follow up delayed material request {request.id}",
                description=issue.description,
                status=TaskStatus.PLANNED,
                priority=_follow_up_priority(issue.severity),
                assigned_to=primary.assigned_to if primary else None,
                trade=primary.trade if primary else None,
                location=primary.location if primary else None,
                planned_start=command.occurred_at,
                planned_end=command.occurred_at,
                source_refs=[command.source_event_id, issue.id, request.id],
                source=TaskSource.WORKFLOW,
                created_at=command.occurred_at,
                updated_at=command.occurred_at,
            )
        )

    @staticmethod
    def _create_blocker_follow_up(
        session: RepositorySession,
        access: ProjectAccessContext,
        command: CreateBlockerFollowUpCommand,
        task_id: str,
    ) -> Task:
        tasks = TaskRepository.for_session(session, access)
        blocked_task = tasks.require(command.project_id, command.blocked_task_id)
        issue = session.repository(Issue).require(command.project_id, command.source_issue_id)
        site_update = session.repository(SiteUpdate).require(
            command.project_id, command.source_site_update_id
        )
        if issue.type is not IssueType.BLOCKER:
            raise TaskStateError("follow-up source issue must be a blocker")
        if blocked_task.id not in issue.task_ids:
            raise TaskStateError("follow-up blocker does not reference the source task")
        if site_update.id not in issue.evidence_refs:
            raise TaskStateError("follow-up blocker does not reference the source site update")
        if blocked_task.status is not TaskStatus.BLOCKED:
            raise TaskStateError("follow-up source task must be blocked")
        return tasks.create(
            Task(
                id=task_id,
                project_id=command.project_id,
                title=f"Follow up: {blocked_task.title}",
                description=issue.description,
                status=TaskStatus.PLANNED,
                priority=_follow_up_priority(issue.severity),
                assigned_to=blocked_task.assigned_to,
                trade=blocked_task.trade,
                location=blocked_task.location,
                planned_start=command.occurred_at,
                planned_end=command.occurred_at,
                source_refs=[site_update.id, issue.id, blocked_task.id],
                source=TaskSource.SITE_UPDATE,
                created_at=command.occurred_at,
                updated_at=command.occurred_at,
            )
        )

    @staticmethod
    def _authorize(
        access: ProjectAccessContext,
        command: UpdateTaskCommand,
        context: MutationContext,
    ) -> None:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")

    @staticmethod
    def _validate_evidence(command: UpdateTaskCommand) -> None:
        if command.negated:
            raise TaskEvidenceRejectedError("negated evidence cannot update task state")
        if command.ambiguous:
            raise TaskEvidenceRejectedError("ambiguous evidence cannot update task state")

    @staticmethod
    def _apply_update(
        session: RepositorySession,
        access: ProjectAccessContext,
        command: UpdateTaskCommand,
        context: MutationContext,
    ) -> Task:
        repository = TaskRepository.for_session(session, access)
        current = repository.require(command.project_id, command.task_id)
        tasks = repository.list(command.project_id)
        by_id = {task.id: task for task in tasks}
        for dependency_id in current.dependency_ids:
            if dependency_id not in by_id:
                raise TaskStateError(f"task references missing dependency {dependency_id}")

        target_status = command.target_status or current.status
        if command.requests_completion:
            target_status = TaskStatus.COMPLETED
        elif (
            command.target_status is None
            and command.completion_percent is not None
            and command.completion_percent > 0
            and current.status is TaskStatus.PLANNED
        ):
            target_status = TaskStatus.IN_PROGRESS
        target_percent = (
            command.completion_percent
            if command.completion_percent is not None
            else current.completion_percent
        )
        if target_status is TaskStatus.CANCELLED:
            raise TaskApprovalRequiredError("task cancellation requires human approval")
        if target_status is TaskStatus.COMPLETED:
            if current.status is TaskStatus.BLOCKED:
                raise TaskBlockedCompletionError("a blocked task cannot be completed")
            incomplete = [
                dependency_id
                for dependency_id in current.dependency_ids
                if by_id[dependency_id].status is not TaskStatus.COMPLETED
            ]
            if incomplete:
                raise TaskDependencyIncompleteError(
                    "task dependencies must be completed first: " + ", ".join(incomplete)
                )
            target_percent = Decimal("100")

        if command.human_correction:
            if context.actor_type is not ActorType.USER:
                raise TaskStateError("human correction requires a user actor")
            if target_percent >= Decimal("100"):
                raise TaskStateError("a reopened task must have completion_percent below 100")

        try:
            ensure_task_transition(
                current.status,
                target_status,
                human_correction=command.human_correction,
                reconciled_completion=command.reconciled_completion,
            )
        except InvalidTransitionError as exc:
            raise TaskStateError(str(exc)) from exc

        actual_start = current.actual_start
        if target_status is TaskStatus.IN_PROGRESS and actual_start is None:
            actual_start = command.occurred_at
        actual_completion = current.actual_completion
        if target_status is TaskStatus.COMPLETED:
            actual_completion = command.occurred_at
        elif current.status is TaskStatus.COMPLETED and target_status is TaskStatus.IN_PROGRESS:
            actual_completion = None

        updated = current.model_copy(
            update={
                "status": target_status,
                "completion_percent": target_percent,
                "actual_start": actual_start,
                "actual_completion": actual_completion,
                "updated_at": command.occurred_at,
            }
        )
        return repository.save(updated, expected_version=command.expected_version)


def _activity_spec(command: UpdateTaskCommand) -> ActivitySpec:
    effective_status = (
        TaskStatus.COMPLETED if command.requests_completion else command.target_status
    )
    status = effective_status.value if effective_status else None
    percent = str(command.completion_percent) if command.completion_percent is not None else None
    evidence_digest = (
        sha256(command.evidence.encode("utf-8")).hexdigest()[:16] if command.evidence else None
    )
    summary = (
        "Task marked complete" if command.requests_completion else "Task progress or status updated"
    )
    return ActivitySpec(
        action=("task.completed" if command.requests_completion else "task.updated"),
        entity_type="task",
        entity_id=command.task_id,
        summary=summary,
        metadata={
            "target_status": status,
            "completion_percent": percent,
            "evidence_digest": evidence_digest,
            "human_correction": command.human_correction,
            "reconciled_completion": command.reconciled_completion,
        },
    )


def _details_activity_spec(command: UpdateTaskDetailsCommand) -> ActivitySpec:
    if command.assigned_to is not None:
        action = "task.assigned"
        summary = "Task assignment updated"
        metadata = {"assignee_id": command.assigned_to}
    elif command.priority is not None:
        action = "task.priority_changed"
        summary = "Task priority updated"
        metadata = {"priority": command.priority.value}
    elif command.planned_end is not None:
        action = "task.due_date_changed"
        summary = "Task due date updated"
        metadata = {"planned_end": command.planned_end.isoformat()}
    else:
        action = "task.note_added"
        summary = "Task note added"
        metadata = {"note_digest": sha256((command.note or "").encode("utf-8")).hexdigest()[:16]}
    return ActivitySpec(
        action=action,
        entity_type="task",
        entity_id=command.task_id,
        summary=summary,
        metadata=metadata,
    )


def _created_task_id(context: MutationContext) -> str:
    raw = f"{context.project_id}\x00{context.actor_id}\x00{context.idempotency_key}"
    return f"tsk_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _follow_up_priority(severity: Severity) -> TaskPriority:
    if severity is Severity.INFO:
        return TaskPriority.LOW
    return TaskPriority(severity.value)


__all__ = [
    "CreateBlockerFollowUpCommand",
    "CreateDeliveryFollowUpCommand",
    "CreateTaskCommand",
    "TaskApprovalRequiredError",
    "TaskBlockedCompletionError",
    "TaskChange",
    "TaskDependencyIncompleteError",
    "TaskEvidenceRejectedError",
    "TaskMutationError",
    "TaskService",
    "TaskStateError",
    "TaskUpdateCommand",
    "UpdateTaskCommand",
    "UpdateTaskDetailsCommand",
]
