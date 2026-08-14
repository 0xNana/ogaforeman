"""Server-side confirmation of durable typed conversation proposals."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from app.domain.activity import MutationContext, activity_id as mutation_activity_id
from app.domain.authorization import ProjectAccessContext
from app.domain.conversation import (
    PendingIssueCommand,
    PendingMaterialCommand,
    PendingScheduleCommand,
    PendingTaskCommand,
)
from app.domain.enums import ActorType
from app.domain.models import ActivityEvent
from app.repositories.interfaces import RepositoryStore, VersionConflictError
from app.repositories.activity import ActivityIdempotencyConflict
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_issue_operations import ConversationIssueService
from app.services.conversation_material_operations import ConversationMaterialService
from app.services.conversation_memory import (
    ConversationMemoryService,
    conversation_command_fingerprint,
)
from app.services.conversation_schedule_operations import ConversationScheduleService
from app.services.conversation_task_operations import ConversationTaskService
from app.services.issues import IssueService
from app.services.materials import MaterialService
from app.services.tasks import TaskService


@dataclass(frozen=True, slots=True)
class ConversationConfirmationResult:
    reply: str
    activity_id: str
    duplicate: bool


class ConversationConfirmationService:
    def __init__(
        self,
        store: RepositoryStore,
        *,
        schedules: ConversationScheduleService | None = None,
        proposal_signing_key: bytes | None = None,
    ) -> None:
        self._store = store
        self._memory = ConversationMemoryService(
            store,
            ConversationEntityResolver(store),
            proposal_signing_key=proposal_signing_key,
        )
        self._tasks = ConversationTaskService(TaskService(store), store)
        self._materials = ConversationMaterialService(MaterialService(store))
        self._issues = ConversationIssueService(IssueService(store), store)
        self._schedules = schedules

    def confirm(
        self,
        access: ProjectAccessContext,
        proposal_id: str,
        observed_memory_version: int,
    ) -> ConversationConfirmationResult:
        consumed = self._memory.claim(access, proposal_id)
        if consumed is not None:
            if consumed.outcome == "confirmed":
                if consumed.activity_id is None or consumed.reply is None:
                    raise RuntimeError("confirmed proposal receipt is incomplete")
                return ConversationConfirmationResult(
                    reply=consumed.reply,
                    activity_id=consumed.activity_id,
                    duplicate=True,
                )
            if consumed.outcome != "confirming":
                raise ValueError("proposal was already consumed without confirmation")
            if consumed.observed_memory_version != observed_memory_version:
                raise ValueError("confirmation memory version does not match reservation")
            if consumed.confirmation_attempt_id is None:
                raise ValueError("confirmation reservation is missing its attempt identity")
            pending = self._memory.require_command(
                access,
                proposal_id,
                observed_memory_version,
                revalidate_state=False,
                revalidate_memory=False,
                allow_reserved_expiry=True,
            )
        else:
            if self._memory.expire_command_if_due(access, proposal_id, observed_memory_version):
                raise ValueError("pending command has expired")
            pending = self._memory.require_command(access, proposal_id, observed_memory_version)
            consumed = self._memory.begin_confirmation(access, pending, observed_memory_version)
        if (
            consumed is not None
            and consumed.command_fingerprint != conversation_command_fingerprint(pending)
        ):
            raise ValueError("confirmation reservation does not match pending command")
        confirmation_attempt_id = consumed.confirmation_attempt_id
        if confirmation_attempt_id is None:
            raise ValueError("confirmation reservation is missing its attempt identity")
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key=pending.idempotency_key,
            request_fingerprint=sha256(
                pending.model_dump_json(exclude={"created_at", "expires_at"}).encode()
            ).hexdigest(),
            confirmation_claim_id=pending.proposal_id,
            confirmation_attempt_id=confirmation_attempt_id,
            confirmation_command_fingerprint=conversation_command_fingerprint(pending),
        )
        try:
            reply, activity_id, duplicate = self._dispatch(access, pending, context)
        except ActivityIdempotencyConflict as exc:
            self._memory.abort_confirmation(access, pending, confirmation_attempt_id)
            raise ValueError("proposal idempotency key identifies another mutation") from exc
        except (ValueError, VersionConflictError, PermissionError):
            existing = self._store.repository(ActivityEvent).get(
                access.project_id, mutation_activity_id(context)
            )
            if not _matches_confirmation(existing, pending):
                self._memory.abort_confirmation(access, pending, confirmation_attempt_id)
                raise
            assert existing is not None
            reply = "Done. The confirmed project change was already applied."
            activity_id = existing.id
            duplicate = True
        self._memory.complete_confirmation(
            access,
            pending,
            activity_id=activity_id,
            reply=reply,
            confirmation_attempt_id=confirmation_attempt_id,
        )
        return ConversationConfirmationResult(reply, activity_id, duplicate)

    def _dispatch(
        self,
        access: ProjectAccessContext,
        pending: PendingTaskCommand
        | PendingMaterialCommand
        | PendingIssueCommand
        | PendingScheduleCommand,
        context: MutationContext,
    ) -> tuple[str, str, bool]:
        if isinstance(pending, PendingTaskCommand):
            task_result = self._tasks.execute(access, pending.command, context)
            return (
                task_result.reply,
                task_result.activity_id,
                task_result.duplicate,
            )
        if isinstance(pending, PendingMaterialCommand):
            material_result = self._materials.execute(access, pending.command, context)
            return (
                material_result.reply,
                material_result.activity_id,
                material_result.duplicate,
            )
        if isinstance(pending, PendingIssueCommand):
            issue_result = self._issues.execute(access, pending.command, context)
            return (
                issue_result.reply,
                issue_result.activity_id,
                issue_result.duplicate,
            )
        if isinstance(pending, PendingScheduleCommand):
            if self._schedules is None:
                raise RuntimeError("schedule confirmation service is unavailable")
            schedule_result = self._schedules.execute(
                access,
                pending.command.model_copy(update={"confirmed": True}),
                context,
            )
            return (
                schedule_result.reply,
                mutation_activity_id(context),
                schedule_result.duplicate,
            )
        raise TypeError("unsupported pending conversation command")


def _matches_confirmation(
    activity: ActivityEvent | None,
    pending: PendingTaskCommand
    | PendingMaterialCommand
    | PendingIssueCommand
    | PendingScheduleCommand,
) -> bool:
    return activity is not None and (
        activity.metadata.get("_confirmation_claim_id") == pending.proposal_id
        and activity.metadata.get("_confirmation_command_fingerprint")
        == conversation_command_fingerprint(pending)
    )


__all__ = ["ConversationConfirmationResult", "ConversationConfirmationService"]
