"""Workflow continuation after approval or rejection."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.models import Approval, AgentRun, MaterialRequest
from app.domain.enums import (
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    MaterialRequestStatus,
)
from app.repositories.interfaces import EntityNotFoundError, RepositorySession, RepositoryStore

logger = logging.getLogger(__name__)


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
    ) -> ApprovalContinuation:
        """Handle an APPROVAL_GRANTED event."""

        def _resume(session: RepositorySession) -> ApprovalContinuation:
            approval_repo = session.repository(Approval)
            approval = approval_repo.require(project_id, approval_id)
            if approval.status is not ApprovalStatus.APPROVED:
                raise RuntimeError("approval continuation requires an approved decision")
            if approval.resolved_by != resolver_id:
                raise RuntimeError("approval continuation resolver does not match persisted state")
            if approval.action_type is not ApprovalActionType.PURCHASE:
                raise RuntimeError("approval continuation only supports purchase approvals")

            req_repo = session.repository(MaterialRequest)
            request = next(
                (item for item in req_repo.list(project_id) if item.approval_id == approval_id),
                None,
            )
            if request is None:
                raise EntityNotFoundError(
                    f"material request for approval {approval_id} was not found"
                )

            run_repo = session.repository(AgentRun)
            run = next(
                (
                    item
                    for item in run_repo.list(project_id)
                    if item.trigger_event_id == request.source_event_id
                ),
                None,
            )
            if run is None:
                raise EntityNotFoundError(
                    f"agent run for material request {request.id} was not found"
                )
            if run.status is AgentRunStatus.WAITING_FOR_APPROVAL:
                run = run_repo.save(
                    run.model_copy(update={"status": AgentRunStatus.RUNNING}),
                    expected_version=run.version,
                )
            elif run.status not in {AgentRunStatus.RUNNING, AgentRunStatus.COMPLETED}:
                raise RuntimeError(f"cannot continue material run in status {run.status.value}")
            return ApprovalContinuation(run_id=run.id, request_id=request.id)

        return self._store.run_transaction(_resume)

    def handle_approval_rejected(self, project_id: str, approval_id: str, resolver_id: str) -> None:
        """Handle an APPROVAL_REJECTED event."""

        def _reject(session: RepositorySession) -> None:
            approval_repo = session.repository(Approval)
            approval = approval_repo.require(project_id, approval_id)

            trigger_event_id = None
            request_to_cancel = None
            if approval.action_type == ApprovalActionType.PURCHASE:
                req_repo = session.repository(MaterialRequest)
                for req in req_repo.list(project_id):
                    if req.approval_id == approval_id:
                        trigger_event_id = req.source_event_id
                        request_to_cancel = req
                        break

            run_to_fail = None
            if trigger_event_id:
                run_repo = session.repository(AgentRun)
                for run in run_repo.list(project_id):
                    if (
                        run.status == AgentRunStatus.WAITING_FOR_APPROVAL
                        and run.trigger_event_id == trigger_event_id
                    ):
                        run_to_fail = run
                        break

            if request_to_cancel is not None:
                req_repo.save(
                    request_to_cancel.model_copy(
                        update={"status": MaterialRequestStatus.CANCELLED}
                    ),
                    expected_version=req_repo.version_of(project_id, request_to_cancel.id),
                )
            if run_to_fail is not None:
                run_repo.save(
                    run_to_fail.model_copy(
                        update={
                            "status": AgentRunStatus.FAILED,
                            "error_code": "APPROVAL_REJECTED",
                            "error_summary": "The required approval was rejected.",
                            "completed_at": datetime.now(UTC),
                        }
                    ),
                    expected_version=run_to_fail.version,
                )

        self._store.run_transaction(_reject)


__all__ = ["ApprovalContinuation", "ResumeWorkflow"]
