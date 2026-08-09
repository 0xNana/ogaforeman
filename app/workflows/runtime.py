"""Durable agent run and checkpoint management."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from app.domain.enums import AgentRunStatus, WorkflowName
from app.domain.models import AgentRun
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.runs import AgentRunRepository


class RuntimeManager:
    """Manages the durable lifecycle and checkpoints of an AgentRun."""

    def __init__(self, store: RepositoryStore) -> None:
        self._runs = AgentRunRepository(store)
        self._store = store

    def start_run(
        self,
        project_id: str,
        trigger_event_id: str,
        workflow: WorkflowName,
        run_id: str,
        trace_id: str,
    ) -> AgentRun:
        """Start or resume an agent run."""

        def _start(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.get(project_id, run_id)
            if run is None:
                run = run_repo.create(
                    AgentRun(
                        id=run_id,
                        project_id=project_id,
                        trigger_event_id=trigger_event_id,
                        workflow=workflow,
                        trace_id=trace_id,
                        status=AgentRunStatus.RUNNING,
                        started_at=datetime.now(UTC),
                    )
                )
            elif run.status in {
                AgentRunStatus.QUEUED,
                AgentRunStatus.WAITING_FOR_APPROVAL,
                AgentRunStatus.WAITING_FOR_CLARIFICATION,
            }:
                run = run.model_copy(update={"status": AgentRunStatus.RUNNING})
                run = run_repo.save(run, expected_version=run.version)
            elif run.status is AgentRunStatus.FAILED:
                run = run.model_copy(
                    update={
                        "status": AgentRunStatus.RUNNING,
                        "attempt": run.attempt + 1,
                        "completed_at": None,
                        "error_code": None,
                        "error_summary": None,
                    }
                )
                run = run_repo.save(run, expected_version=run.version)
            if (
                run.trigger_event_id != trigger_event_id
                or run.workflow is not workflow
                or run.trace_id != trace_id
            ):
                raise RuntimeError("existing agent run does not match its trigger contract")
            return run

        return self._runs.run_transaction(_start)

    def update_checkpoint(self, project_id: str, run_id: str, step: str) -> AgentRun:
        """Update the current step checkpoint for a running agent."""

        def _checkpoint(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            if run.status != AgentRunStatus.RUNNING:
                raise RuntimeError(f"Cannot checkpoint run {run_id} in status {run.status}")
            run = run.model_copy(update={"step": step})
            return run_repo.save(run, expected_version=run.version)

        return self._runs.run_transaction(_checkpoint)

    def pause_for_approval(self, project_id: str, run_id: str, step: str) -> AgentRun:
        """Pause the run to wait for approval."""

        def _pause(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            run = run.model_copy(
                update={"status": AgentRunStatus.WAITING_FOR_APPROVAL, "step": step}
            )
            return run_repo.save(run, expected_version=run.version)

        return self._runs.run_transaction(_pause)

    def pause_for_clarification(self, project_id: str, run_id: str, step: str) -> AgentRun:
        """Pause the run to wait for clarification."""

        def _pause(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            run = run.model_copy(
                update={"status": AgentRunStatus.WAITING_FOR_CLARIFICATION, "step": step}
            )
            return run_repo.save(run, expected_version=run.version)

        return self._runs.run_transaction(_pause)

    def complete_run(self, project_id: str, run_id: str) -> AgentRun:
        """Mark the run as completed successfully."""

        def _complete(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            if run.status is AgentRunStatus.COMPLETED:
                return run
            run = run.model_copy(
                update={"status": AgentRunStatus.COMPLETED, "completed_at": datetime.now(UTC)}
            )
            return run_repo.save(run, expected_version=run.version)

        return self._runs.run_transaction(_complete)

    def fail_run(
        self, project_id: str, run_id: str, error_code: str, error_summary: str
    ) -> AgentRun:
        """Mark the run as failed."""

        def _fail(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            if run.status is AgentRunStatus.COMPLETED:
                return run
            run = run.model_copy(
                update={
                    "status": AgentRunStatus.FAILED,
                    "error_code": error_code,
                    "error_summary": error_summary,
                    "completed_at": datetime.now(UTC),
                }
            )
            return run_repo.save(run, expected_version=run.version)

        return self._runs.run_transaction(_fail)

    def get_run(self, project_id: str, run_id: str) -> AgentRun | None:
        """Get the current state of a run."""
        return self._runs.get(project_id, run_id)


def run_id_for_event(event_id: str) -> str:
    return f"run_{sha256(event_id.encode('utf-8')).hexdigest()[:32]}"


__all__ = ["RuntimeManager", "run_id_for_event"]
