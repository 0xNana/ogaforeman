"""Audited, restart-safe workflow continuation after an approval decision."""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    MaterialRequestStatus,
)
from app.domain.models import ActivityEvent, Approval, AgentRun, MaterialRequest
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import EntityNotFoundError, RepositorySession, RepositoryStore


@dataclass(frozen=True, slots=True)
class ApprovalContinuation:
    run_id: str
    request_id: str


class ResumeWorkflow:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def handle_approval_granted(
        self,
        project_id: str,
        approval_id: str,
        resolver_id: str,
        *,
        source_event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> ApprovalContinuation:
        """Validate an approved decision and atomically resume its original run."""

        transition_at = occurred_at or datetime.now(UTC)

        def _resume(session: RepositorySession) -> ApprovalContinuation:
            approval, request, run = self._load_purchase_branch(
                session,
                project_id,
                approval_id,
            )
            if approval.status is not ApprovalStatus.APPROVED:
                raise RuntimeError("approval continuation requires an approved decision")
            if approval.resolved_by != resolver_id:
                raise RuntimeError("approval continuation resolver does not match persisted state")
            resumed_activity = self._prepare_run_activity(
                session,
                project_id=project_id,
                run=run,
                approval=approval,
                request=request,
                source_event_id=source_event_id or approval.id,
                occurred_at=transition_at,
                action="agent_run.resumed",
                summary="Resumed the workflow after approval.",
                phase="resumed",
            )
            if run.status is AgentRunStatus.WAITING_FOR_APPROVAL:
                run = session.repository(AgentRun).save(
                    run.model_copy(
                        update={
                            "status": AgentRunStatus.RUNNING,
                            "step": "supplier_submission",
                        }
                    ),
                    expected_version=run.version,
                )
            elif run.status not in {AgentRunStatus.RUNNING, AgentRunStatus.COMPLETED}:
                raise RuntimeError(f"cannot continue material run in status {run.status.value}")
            self._create_prepared_activity(session, resumed_activity)
            return ApprovalContinuation(run_id=run.id, request_id=request.id)

        return self._store.run_transaction(_resume)

    def complete_approved_purchase(
        self,
        project_id: str,
        approval_id: str,
        resolver_id: str,
        *,
        source_event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> ApprovalContinuation:
        """Atomically complete the resumed run after its supplier action succeeds."""

        transition_at = occurred_at or datetime.now(UTC)

        def _complete(session: RepositorySession) -> ApprovalContinuation:
            approval, request, run = self._load_purchase_branch(
                session,
                project_id,
                approval_id,
            )
            if approval.status is not ApprovalStatus.APPROVED:
                raise RuntimeError("workflow completion requires an approved decision")
            if approval.resolved_by != resolver_id:
                raise RuntimeError("approval continuation resolver does not match persisted state")
            if request.status not in {
                MaterialRequestStatus.SUBMITTED,
                MaterialRequestStatus.CONFIRMED,
                MaterialRequestStatus.DELAYED,
                MaterialRequestStatus.DELIVERED,
            }:
                raise RuntimeError("supplier action must complete before the workflow run")
            completed_activity = self._prepare_run_activity(
                session,
                project_id=project_id,
                run=run,
                approval=approval,
                request=request,
                source_event_id=source_event_id or approval.id,
                occurred_at=transition_at,
                action="agent_run.completed",
                summary="Completed the approved material workflow.",
                phase="completed",
            )
            if run.status is AgentRunStatus.RUNNING:
                run = session.repository(AgentRun).save(
                    run.model_copy(
                        update={
                            "status": AgentRunStatus.COMPLETED,
                            "step": "completed",
                            "completed_at": transition_at,
                        }
                    ),
                    expected_version=run.version,
                )
            elif run.status is not AgentRunStatus.COMPLETED:
                raise RuntimeError(f"cannot complete material run in status {run.status.value}")
            self._create_prepared_activity(session, completed_activity)
            return ApprovalContinuation(run_id=run.id, request_id=request.id)

        return self._store.run_transaction(_complete)

    def handle_approval_rejected(
        self,
        project_id: str,
        approval_id: str,
        resolver_id: str,
        *,
        source_event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> ApprovalContinuation:
        """Validate rejection and atomically close the original run without side effects."""

        transition_at = occurred_at or datetime.now(UTC)

        def _reject(session: RepositorySession) -> ApprovalContinuation:
            approval, request, run = self._load_purchase_branch(
                session,
                project_id,
                approval_id,
            )
            if approval.status is not ApprovalStatus.REJECTED:
                raise RuntimeError("approval continuation requires a rejected decision")
            if approval.resolved_by != resolver_id:
                raise RuntimeError("approval continuation resolver does not match persisted state")

            request_repo = session.repository(MaterialRequest)
            should_cancel_request = request.status in {
                MaterialRequestStatus.PROPOSED,
                MaterialRequestStatus.AWAITING_APPROVAL,
                MaterialRequestStatus.APPROVED,
            }
            if not should_cancel_request and request.status not in {
                MaterialRequestStatus.CANCELLED,
                MaterialRequestStatus.REJECTED,
            }:
                raise RuntimeError(
                    f"cannot reject material request in status {request.status.value}"
                )
            request_activity = (
                self._prepare_request_cancelled_activity(
                    session,
                    project_id=project_id,
                    run=run,
                    approval=approval,
                    request=request,
                    source_event_id=source_event_id or approval.id,
                    occurred_at=transition_at,
                )
                if should_cancel_request
                else None
            )
            rejected_activity = self._prepare_run_activity(
                session,
                project_id=project_id,
                run=run,
                approval=approval,
                request=request,
                source_event_id=source_event_id or approval.id,
                occurred_at=transition_at,
                action="agent_run.rejected",
                summary="Closed the workflow after the approval was rejected.",
                phase="rejected",
            )

            if should_cancel_request:
                request = request_repo.save(
                    request.model_copy(
                        update={
                            "status": MaterialRequestStatus.CANCELLED,
                            "updated_at": transition_at,
                        }
                    ),
                    expected_version=request_repo.version_of(project_id, request.id),
                )

            run_repo = session.repository(AgentRun)
            if run.status in {
                AgentRunStatus.WAITING_FOR_APPROVAL,
                AgentRunStatus.RUNNING,
            }:
                run = run_repo.save(
                    run.model_copy(
                        update={
                            "status": AgentRunStatus.FAILED,
                            "step": "approval_rejected",
                            "pending_actions": [],
                            "error_code": "APPROVAL_REJECTED",
                            "error_summary": "The required approval was rejected.",
                            "completed_at": transition_at,
                        }
                    ),
                    expected_version=run.version,
                )
            elif not (
                run.status is AgentRunStatus.FAILED and run.error_code == "APPROVAL_REJECTED"
            ):
                raise RuntimeError(f"cannot reject material run in status {run.status.value}")
            self._create_prepared_activity(session, request_activity)
            self._create_prepared_activity(session, rejected_activity)
            return ApprovalContinuation(run_id=run.id, request_id=request.id)

        return self._store.run_transaction(_reject)

    @staticmethod
    def _load_purchase_branch(
        session: RepositorySession,
        project_id: str,
        approval_id: str,
    ) -> tuple[Approval, MaterialRequest, AgentRun]:
        approval = session.repository(Approval).require(project_id, approval_id)
        if approval.action_type is not ApprovalActionType.PURCHASE:
            raise RuntimeError("approval continuation only supports purchase approvals")

        requests = [
            item
            for item in session.repository(MaterialRequest).list(project_id)
            if item.approval_id == approval_id
        ]
        if not requests:
            raise EntityNotFoundError(f"material request for approval {approval_id} was not found")
        if len(requests) > 1:
            raise RuntimeError("approval is linked to more than one material request")
        request = requests[0]

        runs = [
            item
            for item in session.repository(AgentRun).list(project_id)
            if item.trigger_event_id == request.source_event_id
        ]
        if not runs:
            raise EntityNotFoundError(f"agent run for material request {request.id} was not found")
        if len(runs) > 1:
            raise RuntimeError("material request source is linked to more than one agent run")
        return approval, request, runs[0]

    @staticmethod
    def _prepare_run_activity(
        session: RepositorySession,
        *,
        project_id: str,
        run: AgentRun,
        approval: Approval,
        request: MaterialRequest,
        source_event_id: str,
        occurred_at: datetime,
        action: str,
        summary: str,
        phase: str,
    ) -> ActivityEvent | None:
        context = MutationContext(
            project_id=project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=source_event_id,
            agent_run_id=run.id,
            idempotency_key=f"approval-continuation:{approval.id}:{phase}",
            occurred_at=occurred_at,
        )
        spec = ActivitySpec(
            action=action,
            entity_type="agent_run",
            entity_id=run.id,
            summary=summary,
            metadata={
                "approval_id": approval.id,
                "material_request_id": request.id,
                "workflow": run.workflow.value,
            },
        )
        return ResumeWorkflow._prepare_activity(session, context, spec)

    @staticmethod
    def _prepare_request_cancelled_activity(
        session: RepositorySession,
        *,
        project_id: str,
        run: AgentRun,
        approval: Approval,
        request: MaterialRequest,
        source_event_id: str,
        occurred_at: datetime,
    ) -> ActivityEvent | None:
        context = MutationContext(
            project_id=project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=source_event_id,
            agent_run_id=run.id,
            idempotency_key=f"approval-continuation:{approval.id}:request-cancelled",
            occurred_at=occurred_at,
        )
        spec = ActivitySpec(
            action="material_request.cancelled",
            entity_type="material_request",
            entity_id=request.id,
            summary="Cancelled the material request after approval rejection.",
            metadata={"approval_id": approval.id},
        )
        return ResumeWorkflow._prepare_activity(session, context, spec)

    @staticmethod
    def _prepare_activity(
        session: RepositorySession,
        context: MutationContext,
        spec: ActivitySpec,
    ) -> ActivityEvent | None:
        expected = ActivityRepository.build_event(context, spec)
        repository = session.repository(ActivityEvent)
        existing = repository.get(context.project_id, expected.id)
        if existing is None:
            return expected
        ActivityRepository.ensure_replay_matches(existing, expected)
        return None

    @staticmethod
    def _create_prepared_activity(
        session: RepositorySession,
        activity: ActivityEvent | None,
    ) -> None:
        if activity is not None:
            session.repository(ActivityEvent).create(activity)


__all__ = ["ApprovalContinuation", "ResumeWorkflow"]
