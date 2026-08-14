"""Application orchestration from interpreted conversation actions to typed services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from collections.abc import Callable
from typing import Protocol

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.conversation import (
    ContextDomain,
    ContextFocus,
    ContextQuery,
    ConversationIssueCommand,
    ConversationMaterialCommand,
    ConversationPurchaseCommand,
    ConversationTaskCommand,
    ConversationalProjectContext,
    EntityKind,
    EntityResolution,
    IssueOperation,
    MaterialOperation,
    MutationKind,
    MutationPolicyClass,
    MutationPolicyDecision,
    MutationPolicyRequest,
    TaskOperation,
    PendingIssueCommand,
    PendingMaterialCommand,
    PendingScheduleCommand,
    PendingTaskCommand,
    ScheduleChangeCommand,
)
from app.domain.enums import ActorType, TaskStatus
from app.repositories.interfaces import RepositoryStore
from app.services.conversation_action_composer import (
    ActionComposer,
    ActionInterpretation,
    IssueActionInterpretation,
    MaterialActionInterpretation,
    PurchaseActionInterpretation,
    ScheduleActionInterpretation,
    TaskActionInterpretation,
)
from app.services.conversation_context import ProjectContextService, ProjectReader
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_issue_operations import ConversationIssueService
from app.services.conversation_memory import ConversationMemoryService
from app.services.conversation_memory import conversation_proposal_id
from app.services.conversation_material_operations import ConversationMaterialService
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_task_operations import ConversationTaskService
from app.services.conversation_schedule_operations import ConversationScheduleService
from app.services.issues import IssueService
from app.services.materials import MaterialService
from app.services.tasks import TaskService


class ActionInterpreter(Protocol):
    async def interpret(
        self,
        message: str,
        *,
        context: ConversationalProjectContext,
    ) -> ActionInterpretation: ...


@dataclass(frozen=True, slots=True)
class ConversationActionOutcome:
    kind: str
    text: str
    mutation_performed: bool
    activity_id: str | None = None
    proposed_action: str | None = None
    proposal_id: str | None = None
    memory_version: int | None = None
    proposal: (
        PendingTaskCommand
        | PendingMaterialCommand
        | PendingIssueCommand
        | PendingScheduleCommand
        | None
    ) = None


_ACTION_DOMAINS = (
    ContextDomain.PROJECT,
    ContextDomain.TASKS,
    ContextDomain.ISSUES,
    ContextDomain.MATERIALS,
    ContextDomain.MATERIAL_REQUESTS,
    ContextDomain.SCHEDULE,
    ContextDomain.PROJECT_MEMBERS,
)


class ConversationActionExecutionService:
    """Coordinates typed services; it contains no domain persistence implementation."""

    def __init__(
        self,
        store: RepositoryStore,
        projects: ProjectReader,
        interpreter: ActionInterpreter,
        *,
        member_names: Callable[[str], dict[str, str]] | None = None,
        schedules: ConversationScheduleService | None = None,
        proposal_signing_key: bytes | None = None,
    ) -> None:
        self._store = store
        self._interpreter = interpreter
        self._resolver = ConversationEntityResolver(store, member_names=member_names)
        self._policies = MutationPolicyService()
        self._composer = ActionComposer(self._policies)
        self._context = ProjectContextService(store, projects, member_names=member_names)
        self._tasks = ConversationTaskService(TaskService(store), store)
        self._materials = ConversationMaterialService(MaterialService(store))
        self._issues = ConversationIssueService(IssueService(store), store)
        self._memory = ConversationMemoryService(
            store,
            self._resolver,
            self._policies,
            proposal_signing_key=proposal_signing_key,
        )
        self._schedules = schedules

    async def execute(
        self,
        access: ProjectAccessContext,
        message: str,
        *,
        idempotency_key: str,
    ) -> ConversationActionOutcome:
        existing_memory = self._memory.load(access)
        existing = existing_memory.pending_command
        expected_proposal_id = conversation_proposal_id(
            access.project_id, access.actor.user_id, idempotency_key
        )
        if (
            existing is not None
            and (existing.expires_at is None or existing.expires_at <= datetime.now(UTC))
            and existing.proposal_id != expected_proposal_id
        ):
            existing_memory = self._memory.clear_command(
                access, existing.proposal_id, existing_memory.version
            )
            existing = None
        if existing is not None and existing.proposal_id == expected_proposal_id:
            if existing.idempotency_key != idempotency_key or existing.requested_action != message:
                raise ValueError("idempotency key is already bound to another conversation action")
            if existing.expires_at is None or existing.expires_at <= datetime.now(UTC):
                return ConversationActionOutcome(
                    kind="proposal_expired",
                    text="That proposal has expired. Ask OG to prepare the change again.",
                    mutation_performed=False,
                    proposal_id=existing.proposal_id,
                    memory_version=existing_memory.version,
                )
            return ConversationActionOutcome(
                kind="proposed_change",
                text="Review and confirm this project change before OG applies it.",
                mutation_performed=False,
                proposed_action=existing.requested_action,
                proposal_id=existing.proposal_id,
                memory_version=existing_memory.version,
                proposal=existing,
            )
        snapshot = self._context.retrieve(
            access, ContextQuery(domains=_ACTION_DOMAINS, focus=ContextFocus.ALL)
        )
        interpretation = await self._interpreter.interpret(message, context=snapshot)
        resolutions = self._resolve(access, interpretation)
        terms = tuple(
            dict.fromkeys(
                term
                for resolution in resolutions
                for term in resolution.reference.casefold().split()
            )
        )[:8]
        if terms:
            snapshot = self._context.retrieve(
                access,
                ContextQuery(
                    domains=_ACTION_DOMAINS,
                    focus=ContextFocus.ALL,
                    search_terms=terms,
                ),
            )
        policy_request = MutationPolicyRequest(
            project_id=access.project_id,
            kind=_mutation_kind(interpretation, snapshot, resolutions),
        )
        proposal = self._composer.compose(
            access, interpretation, snapshot, resolutions, policy_request
        )
        if proposal.policy_decision.policy is MutationPolicyClass.DENY_OR_ESCALATE:
            return ConversationActionOutcome(
                kind="denied",
                text="I can't apply that project change with your current permission or safety boundary.",
                mutation_performed=False,
            )
        if isinstance(proposal.command, ConversationPurchaseCommand):
            return ConversationActionOutcome(
                kind="needs_approval",
                text="This purchase requires the existing approval workflow before anything can proceed.",
                mutation_performed=False,
                proposed_action=message,
            )
        if proposal.policy_decision.policy is not MutationPolicyClass.AUTO_EXECUTE:
            memory = self._memory.load(access)
            pending = self._pending(
                access,
                proposal.command,
                proposal.policy_decision,
                message,
                idempotency_key,
                observed_memory_version=memory.version,
            )
            if pending.policy_decision.policy is MutationPolicyClass.APPROVAL_REQUIRED:
                return ConversationActionOutcome(
                    kind="needs_approval",
                    text="This change requires the existing approval workflow before anything can proceed.",
                    mutation_performed=False,
                    proposed_action=message,
                )
            if memory.pending_command is not None and _same_pending(
                memory.pending_command, pending
            ):
                pending = memory.pending_command
            else:
                memory = self._memory.remember_command(access, pending)
            if memory.pending_command is None:
                raise RuntimeError("pending proposal persistence returned no command")
            pending = memory.pending_command
            return ConversationActionOutcome(
                kind="proposed_change",
                text="Review and confirm this project change before OG applies it.",
                mutation_performed=False,
                proposed_action=message,
                proposal_id=pending.proposal_id,
                memory_version=memory.version,
                proposal=pending,
            )
        mutation = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key=idempotency_key,
            request_fingerprint=sha256(message.encode("utf-8")).hexdigest(),
        )
        command = proposal.command
        if isinstance(command, ConversationTaskCommand):
            result = self._tasks.execute(access, command, mutation)
            reply, activity_id, duplicate = result.reply, result.activity_id, result.duplicate
        elif isinstance(command, ConversationMaterialCommand):
            material_result = self._materials.execute(access, command, mutation)
            reply, activity_id, duplicate = (
                material_result.reply,
                material_result.activity_id,
                material_result.duplicate,
            )
        elif isinstance(command, ConversationIssueCommand):
            issue_result = self._issues.execute(access, command, mutation)
            reply, activity_id, duplicate = (
                issue_result.reply,
                issue_result.activity_id,
                issue_result.duplicate,
            )
        else:
            raise ValueError("non-routine conversation action requires proposal handling")
        return ConversationActionOutcome(
            kind="done",
            text=(
                "That exact request was already processed; no new mutation was applied."
                if duplicate
                else reply
            ),
            mutation_performed=not duplicate,
            activity_id=activity_id,
        )

    def _pending(
        self,
        access: ProjectAccessContext,
        command: object,
        policy: MutationPolicyDecision,
        requested_action: str,
        idempotency_key: str,
        *,
        observed_memory_version: int,
    ) -> PendingTaskCommand | PendingMaterialCommand | PendingIssueCommand | PendingScheduleCommand:
        proposal_id = conversation_proposal_id(
            access.project_id, access.actor.user_id, idempotency_key
        )
        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(minutes=15)
        if isinstance(command, ConversationTaskCommand):
            task_pending = PendingTaskCommand(
                proposal_id=proposal_id,
                project_id=access.project_id,
                actor_id=access.actor.user_id,
                policy_decision=policy,
                idempotency_key=idempotency_key,
                requested_action=requested_action,
                created_at=created_at,
                expires_at=expires_at,
                observed_memory_version=observed_memory_version,
                observed_entity_versions=_observed_entity_versions(command),
                command=command,
            )
            return self._memory.seal_command(task_pending)
        if isinstance(command, ConversationMaterialCommand):
            material_pending = PendingMaterialCommand(
                proposal_id=proposal_id,
                project_id=access.project_id,
                actor_id=access.actor.user_id,
                policy_decision=policy,
                idempotency_key=idempotency_key,
                requested_action=requested_action,
                created_at=created_at,
                expires_at=expires_at,
                observed_memory_version=observed_memory_version,
                observed_entity_versions=_observed_entity_versions(command),
                command=command,
            )
            return self._memory.seal_command(material_pending)
        if isinstance(command, ConversationIssueCommand):
            issue_pending = PendingIssueCommand(
                proposal_id=proposal_id,
                project_id=access.project_id,
                actor_id=access.actor.user_id,
                policy_decision=policy,
                idempotency_key=idempotency_key,
                requested_action=requested_action,
                created_at=created_at,
                expires_at=expires_at,
                observed_memory_version=observed_memory_version,
                observed_entity_versions=_observed_entity_versions(command),
                command=command,
            )
            return self._memory.seal_command(issue_pending)
        if isinstance(command, ScheduleChangeCommand):
            if self._schedules is None:
                raise RuntimeError("schedule proposal service is unavailable")
            schedule_proposal = self._schedules.propose(access, command)
            kind = (
                MutationKind.MAJOR_SCHEDULE_CHANGE
                if len(schedule_proposal.affected_task_ids) > 3
                else MutationKind.SCHEDULE_DATES
            )
            schedule_policy = self._policies.classify(
                access,
                MutationPolicyRequest(
                    project_id=access.project_id,
                    kind=kind,
                    dependent_entity_count=max(0, len(schedule_proposal.affected_task_ids) - 1),
                ),
            )
            schedule_pending = PendingScheduleCommand(
                proposal_id=proposal_id,
                project_id=access.project_id,
                actor_id=access.actor.user_id,
                policy_decision=schedule_policy,
                idempotency_key=idempotency_key,
                requested_action=requested_action,
                created_at=created_at,
                expires_at=expires_at,
                observed_memory_version=observed_memory_version,
                observed_entity_versions={
                    item.task_id: item.version for item in schedule_proposal.token.affected_versions
                },
                command=command.model_copy(update={"proposal": schedule_proposal.token}),
            )
            return self._memory.seal_command(schedule_pending)
        raise ValueError("purchase approval handoff is not part of routine mutation dispatch")

    def _resolve(
        self,
        access: ProjectAccessContext,
        interpretation: ActionInterpretation,
    ) -> tuple[EntityResolution, ...]:
        references: list[tuple[EntityKind, str | None]]
        if isinstance(interpretation, TaskActionInterpretation):
            references = [
                (EntityKind.TASK, interpretation.task_reference),
                (EntityKind.PROJECT_MEMBER, interpretation.assignee_reference),
            ]
        elif isinstance(interpretation, MaterialActionInterpretation):
            references = [
                (EntityKind.MATERIAL, interpretation.material_reference),
                (EntityKind.MATERIAL_REQUEST, interpretation.material_request_reference),
            ]
        elif isinstance(interpretation, IssueActionInterpretation):
            references = [
                (EntityKind.ISSUE, interpretation.issue_reference),
                (EntityKind.PROJECT_MEMBER, interpretation.owner_reference),
            ]
        elif isinstance(interpretation, ScheduleActionInterpretation):
            references = [(EntityKind.TASK, interpretation.task_reference)]
        elif isinstance(interpretation, PurchaseActionInterpretation):
            references = [(EntityKind.MATERIAL, interpretation.material_reference)]
        else:
            raise TypeError("unsupported action interpretation")
        return tuple(
            self._resolver.resolve(access, kind, reference)
            for kind, reference in references
            if reference is not None
        )


def _mutation_kind(
    interpretation: ActionInterpretation,
    context: ConversationalProjectContext,
    resolutions: tuple[EntityResolution, ...],
) -> MutationKind:
    if isinstance(interpretation, TaskActionInterpretation):
        if interpretation.operation is TaskOperation.CREATE:
            return MutationKind.TASK_CREATE
        if interpretation.operation is TaskOperation.COMPLETE:
            return MutationKind.TASK_COMPLETE
        if interpretation.operation in {TaskOperation.ASSIGN, TaskOperation.REASSIGN}:
            return MutationKind.TASK_ASSIGN
        if interpretation.target_status is TaskStatus.CANCELLED:
            return MutationKind.TASK_CANCEL
        if interpretation.operation is TaskOperation.CHANGE_STATUS:
            task = next((item for item in resolutions if item.kind is EntityKind.TASK), None)
            current = next(
                (
                    item
                    for item in (*context.tasks, *context.schedule)
                    if task and item.id == task.entity_id
                ),
                None,
            )
            if current and current.status == TaskStatus.COMPLETED.value:
                return MutationKind.TASK_REOPEN
        return (
            MutationKind.ADD_NOTE
            if interpretation.operation is TaskOperation.ADD_NOTE
            else MutationKind.TASK_UPDATE
        )
    if isinstance(interpretation, MaterialActionInterpretation):
        if interpretation.operation is MaterialOperation.CREATE:
            return MutationKind.MATERIAL_CREATE
        if interpretation.operation is MaterialOperation.RECORD_DELIVERY:
            return MutationKind.MATERIAL_DELIVERY
        if interpretation.operation in {
            MaterialOperation.SET_ON_SITE,
            MaterialOperation.SET_REQUIRED,
        }:
            return MutationKind.MATERIAL_QUANTITY
        return MutationKind.ADD_NOTE
    if isinstance(interpretation, IssueActionInterpretation):
        if interpretation.operation is IssueOperation.CREATE:
            return MutationKind.ISSUE_CREATE
        if interpretation.operation is IssueOperation.RESOLVE:
            return MutationKind.ISSUE_RESOLVE
        return (
            MutationKind.ADD_NOTE
            if interpretation.operation is IssueOperation.ADD_NOTE
            else MutationKind.ISSUE_UPDATE
        )
    if isinstance(interpretation, ScheduleActionInterpretation):
        return MutationKind.SCHEDULE_DATES
    return MutationKind.MATERIAL_PURCHASE


def _same_pending(left: object, right: object) -> bool:
    if not isinstance(
        left,
        (PendingTaskCommand, PendingMaterialCommand, PendingIssueCommand, PendingScheduleCommand),
    ):
        return False
    if not isinstance(
        right,
        (PendingTaskCommand, PendingMaterialCommand, PendingIssueCommand, PendingScheduleCommand),
    ):
        return False
    return left.model_dump(exclude={"created_at", "expires_at"}) == right.model_dump(
        exclude={"created_at", "expires_at"}
    )


def _observed_entity_versions(
    command: ConversationTaskCommand | ConversationMaterialCommand | ConversationIssueCommand,
) -> dict[str, int]:
    versions: dict[str, int] = {}
    if isinstance(command, ConversationTaskCommand):
        if command.task and command.task.entity_id and command.expected_version is not None:
            versions[command.task.entity_id] = command.expected_version
    elif isinstance(command, ConversationMaterialCommand):
        if command.material and command.material.entity_id and command.expected_version is not None:
            versions[command.material.entity_id] = command.expected_version
        if (
            command.material_request
            and command.material_request.entity_id
            and command.expected_material_request_version is not None
        ):
            versions[command.material_request.entity_id] = command.expected_material_request_version
    elif command.issue and command.issue.entity_id and command.expected_version is not None:
        versions[command.issue.entity_id] = command.expected_version
    return versions


__all__ = ["ActionInterpreter", "ConversationActionExecutionService", "ConversationActionOutcome"]
