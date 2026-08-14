"""Durable, bounded conversational references that are always revalidated."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from pydantic import TypeAdapter

from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.conversation import (
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    IssueOperation,
    MaterialOperation,
    MutationKind,
    MutationPolicyRequest,
    PendingConversationCommand,
    PendingIssueCommand,
    PendingMaterialCommand,
    PendingScheduleCommand,
    PendingTaskCommand,
    TaskOperation,
)
from app.domain.enums import TaskStatus
from app.domain.models import (
    ConversationEntityReference,
    ConversationMemory,
    ConversationProposalClaim,
)
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_mutation_policy import MutationPolicyService


_PENDING_COMMAND_ADAPTER: TypeAdapter[PendingConversationCommand] = TypeAdapter(
    PendingConversationCommand
)


class ConversationMemoryService:
    def __init__(
        self,
        store: RepositoryStore,
        resolver: ConversationEntityResolver,
        policies: MutationPolicyService | None = None,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._policies = policies or MutationPolicyService()

    def load(self, access: ProjectAccessContext) -> ConversationMemory:
        ensure_permission(access, ProjectPermission.READ)
        memory = self._store.repository(ConversationMemory).get(
            access.project_id, _memory_id(access)
        )
        return memory or ConversationMemory(
            id=_memory_id(access), project_id=access.project_id, actor_id=access.actor.user_id
        )

    def remember_reference(
        self,
        access: ProjectAccessContext,
        kind: EntityKind,
        entity_id: str,
        *,
        topic: str | None = None,
    ) -> ConversationMemory:
        resolution = self._resolver.resolve(access, kind, entity_id)
        if resolution.status is not EntityResolutionStatus.RESOLVED or resolution.entity_id is None:
            raise ValueError("only a current project entity can be remembered")
        repository = self._store.repository(ConversationMemory)
        current = self.load(access)
        refs = [
            item
            for item in current.recent_entities
            if not (item.kind == kind.value and item.entity_id == resolution.entity_id)
        ]
        refs.insert(0, ConversationEntityReference(kind=kind.value, entity_id=resolution.entity_id))
        saved = current.model_copy(
            update={
                "recent_entities": refs[:8],
                "recent_topic": topic,
                "updated_at": datetime.now(UTC),
            }
        )
        if repository.get(access.project_id, current.id) is None:
            return repository.create(saved)
        return repository.save(saved, expected_version=current.version)

    def resolve_recent(self, access: ProjectAccessContext, kind: EntityKind) -> EntityResolution:
        reference = next(
            (item for item in self.load(access).recent_entities if item.kind == kind.value), None
        )
        if reference is None:
            return EntityResolution(
                kind=kind, reference="recent context", status=EntityResolutionStatus.NOT_FOUND
            )
        return self._resolver.resolve(access, kind, reference.entity_id)

    def remember_pending(
        self,
        access: ProjectAccessContext,
        *,
        clarification: str | None = None,
        confirmation: str | None = None,
        proposed_action: str | None = None,
    ) -> ConversationMemory:
        repository = self._store.repository(ConversationMemory)
        current = self.load(access)
        if (
            current.pending_clarification == clarification
            and current.pending_confirmation == confirmation
            and current.recent_proposed_action == proposed_action
        ):
            return current
        saved = current.model_copy(
            update={
                "pending_clarification": clarification,
                "pending_confirmation": confirmation,
                "recent_proposed_action": proposed_action,
                "updated_at": datetime.now(UTC),
            }
        )
        if repository.get(access.project_id, current.id) is None:
            return repository.create(saved)
        return repository.save(saved, expected_version=current.version)

    def remember_command(
        self,
        access: ProjectAccessContext,
        command: PendingConversationCommand,
    ) -> ConversationMemory:
        ensure_permission(access, ProjectPermission.OPERATE)
        command = _PENDING_COMMAND_ADAPTER.validate_python(command.model_dump(mode="python"))
        if command.project_id != access.project_id or command.actor_id != access.actor.user_id:
            raise PermissionError("pending command does not match the authorized project actor")
        expected_policy = self._policies.classify(access, _policy_request(command))
        if command.policy_decision != expected_policy:
            raise ValueError("pending command policy does not match deterministic policy")

        def operation(session: RepositorySession) -> ConversationMemory:
            repository = session.repository(ConversationMemory)
            if (
                session.repository(ConversationProposalClaim).get(
                    access.project_id, command.proposal_id
                )
                is not None
            ):
                raise ValueError("a consumed proposal identity cannot be reused")
            current = repository.get(access.project_id, _memory_id(access)) or ConversationMemory(
                id=_memory_id(access),
                project_id=access.project_id,
                actor_id=access.actor.user_id,
            )
            if current.pending_command == command:
                return current
            if current.pending_command is not None:
                if current.pending_command.proposal_id == command.proposal_id:
                    raise ValueError("a proposal identity cannot be reused for different content")
                raise ValueError("another conversational proposal is already pending")
            saved = current.model_copy(
                update={
                    "pending_command": command,
                    "pending_confirmation": None,
                    "recent_proposed_action": command.requested_action,
                    "updated_at": datetime.now(UTC),
                }
            )
            if repository.get(access.project_id, current.id) is None:
                return repository.create(saved)
            return repository.save(saved, expected_version=current.version)

        return self._store.run_transaction(operation)

    def require_command(
        self,
        access: ProjectAccessContext,
        proposal_id: str,
        expected_memory_version: int,
    ) -> PendingConversationCommand:
        memory = self.load(access)
        if memory.version != expected_memory_version:
            raise ValueError("conversation memory changed; reload the pending proposal")
        command = memory.pending_command
        if command is None or command.proposal_id != proposal_id:
            raise ValueError("pending conversational proposal does not match")
        if command.project_id != access.project_id or command.actor_id != access.actor.user_id:
            raise PermissionError("pending command does not match the authorized project actor")
        return command

    def clear_command(
        self,
        access: ProjectAccessContext,
        proposal_id: str,
        expected_memory_version: int,
    ) -> ConversationMemory:
        ensure_permission(access, ProjectPermission.OPERATE)

        def operation(session: RepositorySession) -> ConversationMemory:
            repository = session.repository(ConversationMemory)
            current = repository.require(access.project_id, _memory_id(access))
            claim = session.repository(ConversationProposalClaim).get(
                access.project_id, proposal_id
            )
            if claim is not None:
                if claim.actor_id != access.actor.user_id:
                    raise PermissionError("consumed proposal belongs to another actor")
                return current
            if current.version != expected_memory_version:
                raise ValueError("conversation memory changed; reload the pending proposal")
            if (
                current.pending_command is None
                or current.pending_command.proposal_id != proposal_id
            ):
                raise ValueError("pending conversational proposal does not match")
            command = current.pending_command
            saved = repository.save(
                current.model_copy(
                    update={
                        "pending_command": None,
                        "recent_proposed_action": None,
                        "updated_at": datetime.now(UTC),
                    }
                ),
                expected_version=current.version,
            )
            session.repository(ConversationProposalClaim).create(
                ConversationProposalClaim(
                    id=proposal_id,
                    project_id=access.project_id,
                    actor_id=access.actor.user_id,
                    command_fingerprint=_command_fingerprint(command),
                )
            )
            return saved

        return self._store.run_transaction(operation)


def _policy_request(command: PendingConversationCommand) -> MutationPolicyRequest:
    kind: MutationKind
    dependent_count = 0
    if isinstance(command, PendingTaskCommand):
        operation = command.command.operation
        if operation is TaskOperation.CREATE:
            kind = MutationKind.TASK_CREATE
        elif operation is TaskOperation.COMPLETE:
            kind = MutationKind.TASK_COMPLETE
        elif operation in {TaskOperation.ASSIGN, TaskOperation.REASSIGN}:
            kind = MutationKind.TASK_ASSIGN
        elif (
            operation is TaskOperation.CHANGE_STATUS
            and command.command.target_status is TaskStatus.CANCELLED
        ):
            kind = MutationKind.TASK_CANCEL
        elif operation is TaskOperation.CHANGE_STATUS and command.command.reopening:
            kind = MutationKind.TASK_REOPEN
        elif operation is TaskOperation.ADD_NOTE:
            kind = MutationKind.ADD_NOTE
        else:
            kind = MutationKind.TASK_UPDATE
    elif isinstance(command, PendingMaterialCommand):
        if command.command.requires_material_risk_workflow:
            raise ValueError("material risk commands must use the existing risk workflow")
        material_operation = command.command.operation
        if material_operation is MaterialOperation.CREATE:
            kind = MutationKind.MATERIAL_CREATE
        elif material_operation is MaterialOperation.SET_ON_SITE:
            kind = MutationKind.MATERIAL_QUANTITY
        elif material_operation is MaterialOperation.RECORD_DELIVERY:
            kind = MutationKind.MATERIAL_DELIVERY
        elif material_operation is MaterialOperation.ADD_NOTE:
            kind = MutationKind.ADD_NOTE
        else:
            kind = MutationKind.MATERIAL_UPDATE
    elif isinstance(command, PendingIssueCommand):
        issue_operation = command.command.operation
        if issue_operation is IssueOperation.CREATE:
            kind = MutationKind.ISSUE_CREATE
        elif issue_operation is IssueOperation.RESOLVE:
            kind = MutationKind.ISSUE_RESOLVE
        elif issue_operation is IssueOperation.ADD_NOTE:
            kind = MutationKind.ADD_NOTE
        else:
            kind = MutationKind.ISSUE_UPDATE
    elif isinstance(command, PendingScheduleCommand):
        proposal = command.command.proposal
        dependent_count = max(0, len(proposal.affected_versions) - 1) if proposal else 0
        kind = (
            MutationKind.MAJOR_SCHEDULE_CHANGE
            if dependent_count > 2
            else MutationKind.SCHEDULE_DATES
        )
    else:
        raise TypeError("unsupported pending conversational command")
    return MutationPolicyRequest(
        project_id=command.project_id,
        kind=kind,
        dependent_entity_count=dependent_count,
    )


def _memory_id(access: ProjectAccessContext) -> str:
    digest = sha256(f"{access.project_id}\x00{access.actor.user_id}".encode()).hexdigest()[:24]
    return f"mem_{digest}"


def _command_fingerprint(command: PendingConversationCommand) -> str:
    payload = json.dumps(
        command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return sha256(payload).hexdigest()


__all__ = ["ConversationMemoryService"]
