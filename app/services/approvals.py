"""Approval state machine and continuation service."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType, ApprovalActionType, ApprovalStatus, MaterialRequestStatus
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    Approval,
    MaterialRequest,
    OutboxMessage,
    OutboxStatus,
)
from app.repositories.interfaces import RepositorySession, RepositoryStore, VersionConflictError
from app.repositories.approvals import ApprovalRepository
from app.repositories.activity import ActivityRepository
from app.services.activity import ActivityService
from app.services.outbox import OutboxService


class ApprovalError(ValueError):
    code = "APPROVAL_FAILED"


class ResolutionCommand(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    project_id: str
    approval_id: str
    notes: str | None = Field(default=None, max_length=5_000)
    expected_version: int | None = None
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    approval: Approval
    activity: ActivityEvent | None
    duplicate: bool


class ApprovalService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._activities = ActivityService(store)
        self._outbox = OutboxService(store)

    def _resolve(
        self,
        access: ProjectAccessContext,
        command: ResolutionCommand,
        context: MutationContext,
        status: ApprovalStatus,
    ) -> ApprovalResult:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.APPROVE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")

        spec = ActivitySpec(
            action=f"approval.{status.value}",
            entity_type="approval",
            entity_id=command.approval_id,
            summary=f"Approval {status.value}",
            metadata={
                "notes": command.notes,
            },
        )

        result = self._activities.mutate(
            context,
            spec,
            lambda session: self._apply_resolution(session, access, command, context, status),
            replay=lambda session, activity: self._replay(session, access, command),
        )

        if result.value is None:
            raise RuntimeError("approval replay did not resolve persisted state")

        return ApprovalResult(
            approval=result.value,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    def approve(
        self,
        access: ProjectAccessContext,
        command: ResolutionCommand,
        context: MutationContext,
    ) -> ApprovalResult:
        return self._resolve(access, command, context, ApprovalStatus.APPROVED)

    def reject(
        self,
        access: ProjectAccessContext,
        command: ResolutionCommand,
        context: MutationContext,
    ) -> ApprovalResult:
        return self._resolve(access, command, context, ApprovalStatus.REJECTED)

    def _apply_resolution(
        self,
        session: RepositorySession,
        access: ProjectAccessContext,
        command: ResolutionCommand,
        context: MutationContext,
        status: ApprovalStatus,
    ) -> Approval:
        approvals = ApprovalRepository.for_session(session, access)
        approval = approvals.require(access.project_id, command.approval_id)

        current_version = approvals.version_of(access.project_id, command.approval_id)
        if command.expected_version is not None and current_version != command.expected_version:
            raise VersionConflictError("approval version does not match expected version")

        if approval.status != ApprovalStatus.PENDING:
            if approval.status == status:
                return approval
            raise ApprovalError(f"Approval is already {approval.status.value}")

        linked_request: MaterialRequest | None = None
        linked_request_version: int | None = None
        requests = session.repository(MaterialRequest)
        if approval.action_type is ApprovalActionType.PURCHASE:
            linked_requests = [
                request
                for request in requests.list(command.project_id)
                if request.approval_id == approval.id
            ]
            if len(linked_requests) > 1:
                raise ApprovalError("Approval is linked to more than one material request")
            if linked_requests:
                linked_request = linked_requests[0]
                linked_request_version = requests.version_of(
                    command.project_id,
                    linked_request.id,
                )

        event_type = (
            EventType.APPROVAL_GRANTED
            if status == ApprovalStatus.APPROVED
            else EventType.APPROVAL_REJECTED
        )
        dedup = f"approval_{approval.id}_{status.value}"
        message_id = f"obx_{sha256(dedup.encode('utf-8')).hexdigest()[:20]}"
        outbox = session.repository(OutboxMessage)
        existing_outbox = outbox.get(command.project_id, message_id)

        approval = approval.model_copy(
            update={
                "status": status,
                "resolved_at": command.occurred_at,
                "resolved_by": access.actor.user_id,
                "resolution_notes": command.notes,
            }
        )
        saved_approval = approvals.save(approval, expected_version=command.expected_version)

        if linked_request is not None and linked_request.status in {
            MaterialRequestStatus.PROPOSED,
            MaterialRequestStatus.AWAITING_APPROVAL,
        }:
            request_status = (
                MaterialRequestStatus.APPROVED
                if status is ApprovalStatus.APPROVED
                else MaterialRequestStatus.CANCELLED
            )
            saved_request = requests.save(
                linked_request.model_copy(
                    update={
                        "status": request_status,
                        "updated_at": command.occurred_at,
                    }
                ),
                expected_version=linked_request_version,
            )
            request_activity_context = context.model_copy(
                update={
                    "idempotency_key": (
                        "request-resolution:"
                        + sha256(context.idempotency_key.encode("utf-8")).hexdigest()[:32]
                    )
                }
            )
            session.repository(ActivityEvent).create(
                ActivityRepository.build_event(
                    request_activity_context,
                    ActivitySpec(
                        action=f"material_request.{request_status.value}",
                        entity_type="material_request",
                        entity_id=saved_request.id,
                        summary=f"Material request {request_status.value}.",
                        metadata={"approval_id": saved_approval.id},
                    ),
                )
            )

        event = ProjectEvent(
            event_id=f"evt_{sha256((command.approval_id + status.value + context.idempotency_key).encode()).hexdigest()[:16]}",
            project_id=command.project_id,
            event_type=event_type,
            source=EventSource.SYSTEM,
            occurred_at=command.occurred_at,
            received_at=datetime.now(UTC),
            actor=EventActor(type=EventActorType.USER, id=access.actor.user_id),
            idempotency_key=f"{context.idempotency_key}_outbox",
            correlation_id=context.source_event_id or command.approval_id,
            payload={
                "approval_id": saved_approval.id,
                "resolver": access.actor.user_id,
                "notes": command.notes,
            },
        )

        if existing_outbox is None:
            outbox.create(
                OutboxMessage(
                    id=message_id,
                    project_id=command.project_id,
                    message_type=event_type.value,
                    deduplication_key=dedup,
                    payload=event.model_dump(mode="json"),
                    status=OutboxStatus.PENDING,
                )
            )

        return saved_approval

    def _replay(
        self,
        session: RepositorySession,
        access: ProjectAccessContext,
        command: ResolutionCommand,
    ) -> Approval:
        return ApprovalRepository.for_session(session, access).require(
            access.project_id, command.approval_id
        )


__all__ = ["ApprovalService", "ResolutionCommand", "ApprovalResult", "ApprovalError"]
