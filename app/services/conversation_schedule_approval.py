"""Existing-approval handoff for consequential conversational schedule changes."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectPermission,
    authorize_project_member,
    ensure_permission,
)
from app.domain.conversation import MutationPolicyClass, ScheduleChangeCommand
from app.domain.enums import ActorType, ApprovalActionType, ApprovalStatus
from app.domain.models import ActivityEvent, Approval, ProjectMember
from app.repositories.interfaces import RepositoryStore
from app.services.activity import ActivityService
from app.services.conversation_schedule_operations import (
    ConversationScheduleService,
    ScheduleChangeResult,
)


@dataclass(frozen=True, slots=True)
class ScheduleApprovalResult:
    approval: Approval
    activity: ActivityEvent
    duplicate: bool


class ConversationScheduleApprovalService:
    def __init__(
        self,
        store: RepositoryStore,
        schedules: ConversationScheduleService,
        *,
        approval_signing_key: bytes,
    ) -> None:
        if len(approval_signing_key) < 32:
            raise ValueError("schedule approval signing key must be at least 32 bytes")
        self._store = store
        self._schedules = schedules
        self._activities = ActivityService(store)
        self._approval_signing_key = approval_signing_key

    def prepare(
        self,
        access: ProjectAccessContext,
        command: ScheduleChangeCommand,
        context: MutationContext,
    ) -> ScheduleApprovalResult:
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("schedule approval requester does not match the authorized user")
        proposal = self._schedules.propose(access, command)
        if proposal.policy is not MutationPolicyClass.APPROVAL_REQUIRED:
            raise ValueError("only major schedule changes may enter the approval workflow")
        approved_command = command.model_copy(
            update={"proposal": proposal.token, "confirmed": True}
        )
        approval_id = _approval_id(context)
        command_payload = approved_command.model_dump(mode="json")
        command_fingerprint = _fingerprint(command_payload)
        approval_signature = self._signature(approval_id, command_payload)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="approval.requested",
                entity_type="approval",
                entity_id=approval_id,
                summary="Major schedule change approval requested.",
                metadata={
                    "action_type": ApprovalActionType.SCHEDULE_CHANGE.value,
                    "affected_task_ids": list(proposal.affected_task_ids),
                    "command_fingerprint": command_fingerprint,
                },
            ),
            lambda session: session.repository(Approval).create(
                Approval(
                    id=approval_id,
                    project_id=access.project_id,
                    action_type=ApprovalActionType.SCHEDULE_CHANGE,
                    proposed_action={
                        "schedule_command": command_payload,
                        "command_fingerprint": command_fingerprint,
                        "approval_signature": approval_signature,
                        "affected_task_ids": list(proposal.affected_task_ids),
                    },
                    reason="Major dependency-aware schedule change requires human approval.",
                    evidence_refs=[f"conversation:{context.idempotency_key}"],
                    requested_by=access.actor.user_id,
                    requested_at=context.occurred_at,
                )
            ),
            replay=lambda session, _event: session.repository(Approval).require(
                access.project_id, approval_id
            ),
        )
        if result.value is None:
            raise RuntimeError("schedule approval replay did not resolve persisted state")
        return ScheduleApprovalResult(result.value, result.activity, result.duplicate)

    def continue_approved(
        self,
        project_id: str,
        approval_id: str,
        *,
        source_event_id: str,
        resolver_id: str,
    ) -> ScheduleChangeResult:
        approval = self._store.repository(Approval).require(project_id, approval_id)
        if (
            approval.action_type is not ApprovalActionType.SCHEDULE_CHANGE
            or approval.status is not ApprovalStatus.APPROVED
        ):
            raise ValueError("schedule continuation requires an approved schedule decision")
        if approval.resolved_by != resolver_id:
            raise PermissionError("schedule approval resolver does not match the durable decision")
        payload = approval.proposed_action.get("schedule_command")
        if not isinstance(payload, dict):
            raise ValueError("schedule approval is missing its typed command")
        fingerprint = approval.proposed_action.get("command_fingerprint")
        if not isinstance(fingerprint, str) or fingerprint != _fingerprint(payload):
            raise ValueError("schedule approval command fingerprint is invalid")
        signature = approval.proposed_action.get("approval_signature")
        expected_signature = self._signature(approval.id, payload)
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected_signature):
            raise PermissionError("schedule approval envelope signature is invalid")
        command = ScheduleChangeCommand.model_validate(payload)
        if command.project_id != project_id or command.proposal is None:
            raise ValueError("schedule approval command has invalid project scope")
        membership = next(
            (
                item
                for item in self._store.repository(ProjectMember).list(project_id)
                if item.user_id == approval.requested_by
            ),
            None,
        )
        access = authorize_project_member(
            AuthenticatedUser(
                user_id=approval.requested_by,
                subject="approved-schedule-continuation",
            ),
            project_id,
            membership,
            ProjectPermission.OPERATE,
        )
        return self._schedules.execute_approved(
            access,
            command,
            MutationContext(
                project_id=project_id,
                actor_type=ActorType.SYSTEM,
                source_event_id=source_event_id,
                idempotency_key=f"approved-schedule:{approval.id}",
            ),
            approval,
        )

    def _signature(self, approval_id: str, payload: dict[str, object]) -> str:
        envelope = {
            "approval_id": approval_id,
            "action_type": ApprovalActionType.SCHEDULE_CHANGE.value,
            "schedule_command": payload,
        }
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._approval_signing_key, encoded, sha256).hexdigest()


def _approval_id(context: MutationContext) -> str:
    material = (
        f"{context.project_id}\x00{context.actor_id or 'system'}\x00"
        f"{context.idempotency_key}\x00schedule-approval"
    )
    return f"app_{sha256(material.encode()).hexdigest()[:32]}"


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


__all__ = ["ConversationScheduleApprovalService", "ScheduleApprovalResult"]
