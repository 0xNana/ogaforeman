"""Durable, bounded conversational references that are always revalidated."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import hmac
import json
from secrets import token_hex
from collections.abc import Callable

from pydantic import TypeAdapter

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.conversation import (
    ConversationIssueCommand,
    ConversationMaterialCommand,
    ConversationTaskCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    IssueOperation,
    MaterialOperation,
    MutationKind,
    MutationPolicyClass,
    MutationPolicyRequest,
    PendingConversationCommand,
    PendingIssueCommand,
    PendingMaterialCommand,
    PendingScheduleCommand,
    PendingTaskCommand,
    ScheduleChangeCommand,
    TaskOperation,
)
from app.domain.enums import ActorType, TaskStatus
from app.domain.models import (
    ActivityEvent,
    ConversationEntityReference,
    ConversationMemory,
    ConversationProposalClaim,
    Issue,
    Material,
    MaterialRequest,
    Task,
)
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.activity import ActivityRepository
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.activity import ActivityService


_PENDING_COMMAND_ADAPTER: TypeAdapter[PendingConversationCommand] = TypeAdapter(
    PendingConversationCommand
)


class ConversationMemoryService:
    def __init__(
        self,
        store: RepositoryStore,
        resolver: ConversationEntityResolver,
        policies: MutationPolicyService | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        proposal_signing_key: bytes | None = None,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._policies = policies or MutationPolicyService()
        self._activities = ActivityService(store)
        self._clock = clock or (lambda: datetime.now(UTC))
        if proposal_signing_key is not None and len(proposal_signing_key) < 32:
            raise ValueError("conversation proposal signing key must be at least 32 bytes")
        self._proposal_signing_key = proposal_signing_key

    def seal_command(self, command: PendingConversationCommand) -> PendingConversationCommand:
        if self._proposal_signing_key is None:
            raise RuntimeError("conversation proposal signing is unavailable")
        signature = hmac.new(
            self._proposal_signing_key,
            _signature_payload(command),
            sha256,
        ).hexdigest()
        return _PENDING_COMMAND_ADAPTER.validate_python(
            command.model_copy(update={"signature": signature}).model_dump(mode="python")
        )

    def _verify_signature(self, command: PendingConversationCommand) -> None:
        if self._proposal_signing_key is None:
            return
        if command.signature is None:
            raise ValueError("pending command is missing its server signature")
        expected = hmac.new(
            self._proposal_signing_key,
            _signature_payload(command),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(command.signature, expected):
            raise ValueError("pending command server signature is invalid")

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
        self._verify_signature(command)
        if command.project_id != access.project_id or command.actor_id != access.actor.user_id:
            raise PermissionError("pending command does not match the authorized project actor")
        expected_policy = self._policies.classify(access, _policy_request(command))
        if command.policy_decision != expected_policy:
            raise ValueError("pending command policy does not match deterministic policy")
        if command.policy_decision.policy is not MutationPolicyClass.CONFIRM_FIRST:
            raise ValueError("only confirm-first commands may be persisted as pending")
        if command.proposal_id != conversation_proposal_id(
            command.project_id, command.actor_id, command.idempotency_key
        ):
            raise ValueError("pending command proposal identity is not server-derived")
        if command.observed_memory_version is None or command.expires_at is None:
            raise ValueError("pending command is missing server lifecycle fields")
        if (command.expires_at - command.created_at).total_seconds() != 900:
            raise ValueError("pending command lifetime must be exactly 15 minutes")
        if command.created_at > self._clock():
            raise ValueError("pending command creation time cannot be in the future")
        if command.observed_entity_versions != _entity_versions(command):
            raise ValueError("pending command observed entity versions do not match its payload")
        if command.expires_at is not None and command.expires_at <= self._clock():
            raise ValueError("pending command has expired")
        if (
            self._store.repository(ConversationProposalClaim).get(
                access.project_id, command.proposal_id
            )
            is not None
        ):
            raise ValueError("a consumed proposal identity cannot be reused")
        observed = self._store.repository(ConversationMemory).get(
            access.project_id, _memory_id(access)
        )
        if (
            observed is not None
            and observed.pending_command is not None
            and not _is_expired(observed.pending_command, self._clock())
        ):
            if _same_proposal(observed.pending_command, command):
                pass
            elif observed.pending_command.proposal_id == command.proposal_id:
                raise ValueError("a proposal identity cannot be reused for different content")
            else:
                raise ValueError("another conversational proposal is already pending")

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
            if current.pending_command == command or (
                current.pending_command is not None
                and _same_proposal(current.pending_command, command)
            ):
                return current
            if current.version != command.observed_memory_version:
                raise ValueError("conversation memory changed; rebuild the pending proposal")
            if current.pending_command is not None and _is_expired(
                current.pending_command, self._clock()
            ):
                _expire_pending_in_session(
                    session,
                    access,
                    current.pending_command,
                    self._clock(),
                )
            elif current.pending_command is not None:
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

        command_fingerprint = conversation_command_fingerprint(command)
        audit_key = f"conversation-proposal:{sha256(command.idempotency_key.encode()).hexdigest()}"
        result = self._activities.mutate(
            MutationContext(
                project_id=access.project_id,
                actor_type=ActorType.USER,
                actor_id=access.actor.user_id,
                idempotency_key=audit_key,
                request_fingerprint=command_fingerprint,
            ),
            ActivitySpec(
                action="conversation.proposal_created",
                entity_type="conversation_memory",
                entity_id=_memory_id(access),
                summary="Conversation change proposed for review.",
                metadata={
                    "proposal_id": command.proposal_id,
                    "command_kind": command.kind,
                    "policy": command.policy_decision.policy.value,
                    "command_fingerprint": command_fingerprint,
                },
            ),
            operation,
            replay=lambda session, _event: session.repository(ConversationMemory).require(
                access.project_id, _memory_id(access)
            ),
        )
        if result.value is None:
            raise RuntimeError("proposal audit replay did not recover conversation memory")
        return result.value

    def require_command(
        self,
        access: ProjectAccessContext,
        proposal_id: str,
        expected_memory_version: int,
        *,
        revalidate_state: bool = True,
        revalidate_memory: bool = True,
        allow_reserved_expiry: bool = False,
    ) -> PendingConversationCommand:
        memory = self.load(access)
        if revalidate_memory and memory.version != expected_memory_version:
            raise ValueError("conversation memory changed; reload the pending proposal")
        command = memory.pending_command
        if command is None or command.proposal_id != proposal_id:
            raise ValueError("pending conversational proposal does not match")
        if command.project_id != access.project_id or command.actor_id != access.actor.user_id:
            raise PermissionError("pending command does not match the authorized project actor")
        self._verify_signature(command)
        expected_policy = self._policies.classify(access, _policy_request(command))
        if (
            command.policy_decision != expected_policy
            or command.policy_decision.policy is not MutationPolicyClass.CONFIRM_FIRST
        ):
            raise ValueError("pending command is not an authorized confirm-first proposal")
        if command.proposal_id != conversation_proposal_id(
            command.project_id, command.actor_id, command.idempotency_key
        ):
            raise ValueError("pending command proposal identity is not server-derived")
        if command.expires_at is None:
            raise ValueError("legacy pending command must be rebuilt before execution")
        if (command.expires_at - command.created_at).total_seconds() != 900:
            raise ValueError("pending command lifetime is invalid")
        if command.created_at > self._clock():
            raise ValueError("pending command creation time is invalid")
        if command.expires_at <= self._clock() and not allow_reserved_expiry:
            raise ValueError("pending command has expired")
        if command.observed_memory_version is None:
            raise ValueError("pending command is missing its observed memory version")
        if command.observed_entity_versions != _entity_versions(command):
            raise ValueError("pending command observed entity versions are invalid")
        if revalidate_state:
            for entity_id, observed_version in command.observed_entity_versions.items():
                current_version = _current_entity_version(self._store, access.project_id, entity_id)
                if current_version != observed_version:
                    raise ValueError("pending command target state is stale; rebuild the proposal")
        return command

    def begin_confirmation(
        self,
        access: ProjectAccessContext,
        command: PendingConversationCommand,
        expected_memory_version: int,
    ) -> ConversationProposalClaim:
        attempt_id = token_hex(16)
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key=f"conversation-confirm-start:{command.proposal_id}",
        )

        def reserve(session: RepositorySession) -> ConversationProposalClaim:
            memory = session.repository(ConversationMemory).require(
                access.project_id, _memory_id(access)
            )
            if memory.version != expected_memory_version or memory.pending_command != command:
                raise ValueError("pending proposal changed before confirmation")
            claims = session.repository(ConversationProposalClaim)
            existing = claims.get(access.project_id, command.proposal_id)
            if existing is not None:
                if existing.actor_id != access.actor.user_id:
                    raise PermissionError("consumed proposal belongs to another actor")
                return existing
            return claims.create(
                ConversationProposalClaim(
                    id=command.proposal_id,
                    project_id=access.project_id,
                    actor_id=access.actor.user_id,
                    command_fingerprint=conversation_command_fingerprint(command),
                    outcome="confirming",
                    observed_memory_version=expected_memory_version,
                    confirmation_attempt_id=attempt_id,
                )
            )

        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="conversation.proposal_confirmation_started",
                entity_type="conversation_proposal",
                entity_id=command.proposal_id,
                summary="Conversation proposal reserved for confirmation.",
                metadata={"proposal_id": command.proposal_id},
            ),
            reserve,
            replay=lambda session, _event: session.repository(ConversationProposalClaim).require(
                access.project_id, command.proposal_id
            ),
        )
        if result.value is None:
            raise RuntimeError("confirmation reservation did not persist")
        return result.value

    def expire_command_if_due(
        self,
        access: ProjectAccessContext,
        proposal_id: str,
        expected_memory_version: int,
    ) -> bool:
        ensure_permission(access, ProjectPermission.OPERATE)

        def expire(session: RepositorySession) -> bool:
            repository = session.repository(ConversationMemory)
            memory = repository.require(access.project_id, _memory_id(access))
            command = memory.pending_command
            if command is None or command.proposal_id != proposal_id:
                return False
            if memory.version != expected_memory_version:
                raise ValueError("conversation memory changed; reload the pending proposal")
            if not _is_expired(command, self._clock()):
                return False
            _expire_pending_in_session(session, access, command, self._clock())
            repository.save(
                memory.model_copy(
                    update={
                        "pending_command": None,
                        "recent_proposed_action": None,
                        "updated_at": self._clock(),
                    }
                ),
                expected_version=memory.version,
            )
            return True

        return self._store.run_transaction(expire)

    def complete_confirmation(
        self,
        access: ProjectAccessContext,
        command: PendingConversationCommand,
        *,
        activity_id: str,
        reply: str,
        confirmation_attempt_id: str,
    ) -> ConversationProposalClaim:
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key=f"conversation-confirm-complete:{command.proposal_id}",
        )

        def complete(session: RepositorySession) -> ConversationProposalClaim:
            claims = session.repository(ConversationProposalClaim)
            claim = claims.require(access.project_id, command.proposal_id)
            if claim.actor_id != access.actor.user_id:
                raise PermissionError("consumed proposal belongs to another actor")
            if claim.command_fingerprint != conversation_command_fingerprint(command):
                raise ValueError("confirmation reservation command changed")
            if claim.confirmation_attempt_id != confirmation_attempt_id:
                raise ValueError("confirmation attempt was superseded")
            if claim.outcome == "confirmed":
                return claim
            if claim.outcome != "confirming":
                raise ValueError("proposal was consumed without confirmation")
            memory_repository = session.repository(ConversationMemory)
            memory = memory_repository.require(access.project_id, _memory_id(access))
            if memory.pending_command != command:
                raise ValueError("pending proposal changed during confirmation")
            memory_repository.save(
                memory.model_copy(
                    update={
                        "pending_command": None,
                        "recent_proposed_action": None,
                        "updated_at": self._clock(),
                    }
                ),
                expected_version=memory.version,
            )
            claim_version = claims.version_of(access.project_id, command.proposal_id)
            if claim_version is None:
                raise RuntimeError("confirmation reservation has no version")
            return claims.save(
                claim.model_copy(
                    update={
                        "outcome": "confirmed",
                        "activity_id": activity_id,
                        "reply": reply,
                        "consumed_at": self._clock(),
                    }
                ),
                expected_version=claim_version,
            )

        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="conversation.proposal_confirmed",
                entity_type="conversation_proposal",
                entity_id=command.proposal_id,
                summary="Conversation proposal confirmed and consumed.",
                metadata={"proposal_id": command.proposal_id, "activity_id": activity_id},
            ),
            complete,
            replay=lambda session, _event: session.repository(ConversationProposalClaim).require(
                access.project_id, command.proposal_id
            ),
        )
        if result.value is None:
            raise RuntimeError("confirmation receipt did not persist")
        return result.value

    def clear_command(
        self,
        access: ProjectAccessContext,
        proposal_id: str,
        expected_memory_version: int,
        *,
        outcome: str = "cancelled",
        activity_id: str | None = None,
        reply: str | None = None,
        allow_memory_drift: bool = False,
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
                if claim.outcome == "cancelled":
                    return current
                raise ValueError("proposal is reserved or already consumed")
            if not allow_memory_drift and current.version != expected_memory_version:
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
                    command_fingerprint=conversation_command_fingerprint(command),
                    outcome=outcome,
                    activity_id=activity_id,
                    reply=reply,
                )
            )
            return saved

        result = self._activities.mutate(
            MutationContext(
                project_id=access.project_id,
                actor_type=ActorType.USER,
                actor_id=access.actor.user_id,
                idempotency_key=f"conversation-clear:{proposal_id}",
            ),
            ActivitySpec(
                action="conversation.proposal_cleared",
                entity_type="conversation_memory",
                entity_id=_memory_id(access),
                summary="Conversation proposal cleared.",
                metadata={"proposal_id": proposal_id},
            ),
            operation,
            replay=lambda session, _event: session.repository(ConversationMemory).require(
                access.project_id, _memory_id(access)
            ),
        )
        if result.value is None:
            raise RuntimeError("proposal clear replay did not recover conversation memory")
        return result.value

    def abort_confirmation(
        self,
        access: ProjectAccessContext,
        command: PendingConversationCommand,
        confirmation_attempt_id: str,
    ) -> ConversationProposalClaim:
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key=f"conversation-confirm-abort:{command.proposal_id}",
        )

        def abort(session: RepositorySession) -> ConversationProposalClaim:
            claims = session.repository(ConversationProposalClaim)
            claim = claims.require(access.project_id, command.proposal_id)
            if claim.actor_id != access.actor.user_id or claim.outcome != "confirming":
                raise ValueError("proposal is not an active confirmation reservation")
            if claim.command_fingerprint != conversation_command_fingerprint(command):
                raise ValueError("confirmation reservation command changed")
            if claim.confirmation_attempt_id != confirmation_attempt_id:
                raise ValueError("confirmation attempt was superseded")
            memory_repository = session.repository(ConversationMemory)
            memory = memory_repository.require(access.project_id, _memory_id(access))
            if memory.pending_command != command:
                raise ValueError("pending proposal changed during confirmation")
            memory_repository.save(
                memory.model_copy(
                    update={
                        "pending_command": None,
                        "recent_proposed_action": None,
                        "updated_at": self._clock(),
                    }
                ),
                expected_version=memory.version,
            )
            claim_version = claims.version_of(access.project_id, command.proposal_id)
            if claim_version is None:
                raise RuntimeError("confirmation reservation has no version")
            return claims.save(
                claim.model_copy(update={"outcome": "stale", "consumed_at": self._clock()}),
                expected_version=claim_version,
            )

        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="conversation.proposal_confirmation_aborted",
                entity_type="conversation_proposal",
                entity_id=command.proposal_id,
                summary="Stale conversation proposal confirmation aborted.",
                metadata={"proposal_id": command.proposal_id, "reason_code": "stale_state"},
            ),
            abort,
            replay=lambda session, _event: session.repository(ConversationProposalClaim).require(
                access.project_id, command.proposal_id
            ),
        )
        if result.value is None:
            raise RuntimeError("confirmation abort receipt did not persist")
        return result.value

    def claim(
        self, access: ProjectAccessContext, proposal_id: str
    ) -> ConversationProposalClaim | None:
        ensure_permission(access, ProjectPermission.OPERATE)
        claim = self._store.repository(ConversationProposalClaim).get(
            access.project_id, proposal_id
        )
        if claim is not None and claim.actor_id != access.actor.user_id:
            raise PermissionError("consumed proposal belongs to another actor")
        return claim


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


def conversation_command_fingerprint(command: PendingConversationCommand) -> str:
    payload = json.dumps(
        command.model_dump(mode="json", exclude={"created_at", "expires_at", "signature"}),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(payload).hexdigest()


def conversation_proposal_id(project_id: str, actor_id: str, idempotency_key: str) -> str:
    raw = f"{project_id}\x00{actor_id}\x00{idempotency_key}".encode()
    return f"cpr_{sha256(raw).hexdigest()[:32]}"


def _same_proposal(left: PendingConversationCommand, right: PendingConversationCommand) -> bool:
    return left.model_dump(exclude={"created_at", "expires_at", "signature"}) == right.model_dump(
        exclude={"created_at", "expires_at", "signature"}
    )


def _is_expired(command: PendingConversationCommand, now: datetime) -> bool:
    return command.expires_at is not None and command.expires_at <= now


def _expire_pending_in_session(
    session: RepositorySession,
    access: ProjectAccessContext,
    command: PendingConversationCommand,
    expired_at: datetime,
) -> None:
    claims = session.repository(ConversationProposalClaim)
    existing_claim = claims.get(access.project_id, command.proposal_id)
    if existing_claim is not None and existing_claim.outcome != "expired":
        raise ValueError("reserved or consumed proposal cannot be replaced as expired")
    if existing_claim is None:
        claims.create(
            ConversationProposalClaim(
                id=command.proposal_id,
                project_id=access.project_id,
                actor_id=access.actor.user_id,
                command_fingerprint=conversation_command_fingerprint(command),
                outcome="expired",
                consumed_at=expired_at,
            )
        )
    expiry_context = MutationContext(
        project_id=access.project_id,
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key=f"conversation-expire:{command.proposal_id}",
    )
    expiry_spec = ActivitySpec(
        action="conversation.proposal_expired",
        entity_type="conversation_proposal",
        entity_id=command.proposal_id,
        summary="Expired conversation proposal replaced.",
        metadata={"proposal_id": command.proposal_id},
    )
    expected = ActivityRepository.build_event(expiry_context, expiry_spec)
    activities = session.repository(ActivityEvent)
    existing_activity = activities.get(access.project_id, expected.id)
    if existing_activity is None:
        activities.create(expected)
    else:
        ActivityRepository.ensure_replay_matches(existing_activity, expected)


def _signature_payload(command: PendingConversationCommand) -> bytes:
    return json.dumps(
        command.model_dump(mode="json", exclude={"signature"}),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _current_entity_version(store: RepositoryStore, project_id: str, entity_id: str) -> int | None:
    if entity_id.startswith("tsk_"):
        return store.repository(Task).version_of(project_id, entity_id)
    if entity_id.startswith("mat_"):
        return store.repository(Material).version_of(project_id, entity_id)
    if entity_id.startswith("mreq_"):
        return store.repository(MaterialRequest).version_of(project_id, entity_id)
    if entity_id.startswith("iss_"):
        return store.repository(Issue).version_of(project_id, entity_id)
    raise ValueError("pending command contains an unsupported versioned entity")


def _entity_versions(command: PendingConversationCommand) -> dict[str, int]:
    payload = command.command
    if isinstance(command, PendingTaskCommand):
        assert isinstance(payload, ConversationTaskCommand)
        if payload.task and payload.task.entity_id and payload.expected_version is not None:
            return {payload.task.entity_id: payload.expected_version}
        return {}
    if isinstance(command, PendingMaterialCommand):
        assert isinstance(payload, ConversationMaterialCommand)
        versions: dict[str, int] = {}
        if payload.material and payload.material.entity_id and payload.expected_version is not None:
            versions[payload.material.entity_id] = payload.expected_version
        if (
            payload.material_request
            and payload.material_request.entity_id
            and payload.expected_material_request_version is not None
        ):
            versions[payload.material_request.entity_id] = payload.expected_material_request_version
        return versions
    if isinstance(command, PendingIssueCommand):
        assert isinstance(payload, ConversationIssueCommand)
        if payload.issue and payload.issue.entity_id and payload.expected_version is not None:
            return {payload.issue.entity_id: payload.expected_version}
        return {}
    assert isinstance(payload, ScheduleChangeCommand)
    proposal = payload.proposal
    if proposal is None:
        return {}
    return {item.task_id: item.version for item in proposal.affected_versions}


__all__ = [
    "ConversationMemoryService",
    "conversation_command_fingerprint",
    "conversation_proposal_id",
]
