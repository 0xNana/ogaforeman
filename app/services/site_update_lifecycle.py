"""Atomic, audited execution state for persisted site updates and agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Callable, Sequence
from hashlib import sha256

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.enums import ActorType, AgentRunStatus, ProcessingStatus, WorkflowName
from app.domain.models import AgentRun, SiteUpdate
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.services.activity import ActivityService


TransitionMutation = Callable[[RepositorySession, datetime], SiteUpdate]


class InvalidSiteUpdateTransition(RuntimeError):
    code = "INVALID_SITE_UPDATE_TRANSITION"


@dataclass(frozen=True, slots=True)
class SiteUpdateExecutionState:
    update: SiteUpdate
    run: AgentRun


class SiteUpdateExecutionStateService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._activities = ActivityService(store)

    def start_attempt(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        attempt: int,
    ) -> SiteUpdateExecutionState:
        if attempt < 1:
            raise ValueError("attempt must be positive")

        def mutation(session: RepositorySession, now: datetime) -> SiteUpdate:
            update_repo = session.repository(SiteUpdate)
            run_repo = session.repository(AgentRun)
            update = update_repo.require(access.project_id, update_id)
            run = run_repo.require(access.project_id, run_id)
            self._validate_run_contract(run, source_event_id, trace_id)
            if update.processing_status not in {
                ProcessingStatus.RECEIVED,
                ProcessingStatus.PROCESSING,
                ProcessingStatus.FAILED,
            }:
                raise InvalidSiteUpdateTransition(
                    f"cannot start processing from {update.processing_status}"
                )
            if run.status not in {
                AgentRunStatus.QUEUED,
                AgentRunStatus.RUNNING,
                AgentRunStatus.FAILED,
            }:
                raise InvalidSiteUpdateTransition(f"cannot start run from {run.status}")
            if attempt < run.attempt:
                raise InvalidSiteUpdateTransition("event claim attempt is older than agent run")
            update_version = update_repo.version_of(access.project_id, update_id)
            run_version = run_repo.version_of(access.project_id, run_id)
            if update_version is None or run_version is None:
                raise RuntimeError("site update execution state disappeared")
            saved_update = update_repo.save(
                update.model_copy(
                    update={
                        "processing_status": ProcessingStatus.PROCESSING,
                        "processed_at": None,
                        "updated_at": now,
                    }
                ),
                expected_version=update_version,
            )
            run_repo.save(
                run.model_copy(
                    update={
                        "status": AgentRunStatus.RUNNING,
                        "attempt": attempt,
                        "completed_at": None,
                        "result_summary": None,
                        "pending_actions": [],
                        "error_code": None,
                        "error_summary": None,
                    }
                ),
                expected_version=run_version,
            )
            return saved_update

        return self._transition(
            access,
            update_id,
            source_event_id=source_event_id,
            run_id=run_id,
            attempt=attempt,
            idempotency_key=f"site-update:{update_id}:processing:{attempt}",
            action="site_update.processing_started",
            summary="Site update processing started.",
            target=ProcessingStatus.PROCESSING,
            mutation=mutation,
        )

    def complete(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        attempt: int,
        result_summary: str,
        pending_actions: Sequence[str],
    ) -> SiteUpdateExecutionState:
        def mutation(session: RepositorySession, now: datetime) -> SiteUpdate:
            return self._finish(
                session,
                access,
                update_id,
                source_event_id=source_event_id,
                run_id=run_id,
                trace_id=trace_id,
                update_status=ProcessingStatus.COMPLETED,
                run_status=AgentRunStatus.COMPLETED,
                now=now,
                result_summary=result_summary,
                pending_actions=pending_actions,
            )

        return self._transition(
            access,
            update_id,
            source_event_id=source_event_id,
            run_id=run_id,
            attempt=attempt,
            idempotency_key=f"site-update:{update_id}:completed",
            action="site_update.processing_completed",
            summary="Site update processing completed.",
            target=ProcessingStatus.COMPLETED,
            mutation=mutation,
        )

    def persist_transcript(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        transcript: str,
        attachment_ids: list[str],
    ) -> SiteUpdate:
        normalized = transcript.strip()
        if not normalized:
            raise ValueError("voice transcription returned no speech")

        now = datetime.now(UTC)
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            source_event_id=source_event_id,
            agent_run_id=run_id,
            idempotency_key=f"site-update:{update_id}:transcribed",
            occurred_at=now,
        )

        def mutation(session: RepositorySession) -> SiteUpdate:
            update_repo = session.repository(SiteUpdate)
            run = session.repository(AgentRun).require(access.project_id, run_id)
            self._validate_run_contract(run, source_event_id, trace_id)
            update = update_repo.require(access.project_id, update_id)
            if update.processing_status is not ProcessingStatus.PROCESSING:
                raise InvalidSiteUpdateTransition(
                    f"cannot persist transcript from {update.processing_status}"
                )
            if run.status is not AgentRunStatus.RUNNING:
                raise InvalidSiteUpdateTransition(
                    "agent run cannot persist a transcript from its current state"
                )
            if not set(attachment_ids).issubset(update.attachment_ids):
                raise InvalidSiteUpdateTransition(
                    "transcribed attachment does not belong to the site update"
                )
            version = update_repo.version_of(access.project_id, update_id)
            if version is None:
                raise RuntimeError("site update disappeared during transcription")
            return update_repo.save(
                update.model_copy(
                    update={
                        "transcript": normalized,
                        "transcribed_attachment_ids": attachment_ids,
                        "updated_at": now,
                    }
                ),
                expected_version=version,
            )

        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="site_update.transcribed",
                entity_type="site_update",
                entity_id=update_id,
                summary="Voice attachment transcribed.",
                metadata={
                    "attachment_ids": attachment_ids,
                    "transcript_digest": sha256(normalized.encode("utf-8")).hexdigest()[:20],
                },
            ),
            mutation,
            replay=lambda session, _activity: session.repository(SiteUpdate).require(
                access.project_id, update_id
            ),
        )
        if result.value is None:
            raise RuntimeError("transcript persistence replay did not resolve site update")
        return result.value

    def wait_for_clarification(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        attempt: int,
        step: str,
        result_summary: str,
        pending_actions: Sequence[str],
    ) -> SiteUpdateExecutionState:
        def mutation(session: RepositorySession, now: datetime) -> SiteUpdate:
            update_repo = session.repository(SiteUpdate)
            run_repo = session.repository(AgentRun)
            update = update_repo.require(access.project_id, update_id)
            run = run_repo.require(access.project_id, run_id)
            self._validate_run_contract(run, source_event_id, trace_id)
            if update.processing_status is not ProcessingStatus.PROCESSING:
                raise InvalidSiteUpdateTransition(
                    f"cannot request clarification from {update.processing_status}"
                )
            if run.status is not AgentRunStatus.RUNNING:
                raise InvalidSiteUpdateTransition("agent run cannot wait from its current state")
            update_version = update_repo.version_of(access.project_id, update_id)
            run_version = run_repo.version_of(access.project_id, run_id)
            if update_version is None or run_version is None:
                raise RuntimeError("site update execution state disappeared")
            saved_update = update_repo.save(
                update.model_copy(
                    update={
                        "processing_status": ProcessingStatus.WAITING_FOR_CLARIFICATION,
                        "updated_at": now,
                    }
                ),
                expected_version=update_version,
            )
            run_repo.save(
                run.model_copy(
                    update={
                        "status": AgentRunStatus.WAITING_FOR_CLARIFICATION,
                        "step": step,
                        "result_summary": result_summary,
                        "pending_actions": list(pending_actions),
                    }
                ),
                expected_version=run_version,
            )
            return saved_update

        return self._transition(
            access,
            update_id,
            source_event_id=source_event_id,
            run_id=run_id,
            attempt=attempt,
            idempotency_key=f"site-update:{update_id}:clarification",
            action="site_update.clarification_requested",
            summary="Site update requires clarification.",
            target=ProcessingStatus.WAITING_FOR_CLARIFICATION,
            mutation=mutation,
        )

    def wait_for_approval(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        attempt: int,
        step: str,
        result_summary: str,
        pending_actions: Sequence[str],
    ) -> SiteUpdateExecutionState:
        def mutation(session: RepositorySession, now: datetime) -> SiteUpdate:
            update_repo = session.repository(SiteUpdate)
            run_repo = session.repository(AgentRun)
            update = update_repo.require(access.project_id, update_id)
            run = run_repo.require(access.project_id, run_id)
            self._validate_run_contract(run, source_event_id, trace_id)
            if update.processing_status is not ProcessingStatus.PROCESSING:
                raise InvalidSiteUpdateTransition(
                    f"cannot request approval from {update.processing_status}"
                )
            if run.status is not AgentRunStatus.RUNNING:
                raise InvalidSiteUpdateTransition("agent run cannot wait from its current state")
            update_version = update_repo.version_of(access.project_id, update_id)
            run_version = run_repo.version_of(access.project_id, run_id)
            if update_version is None or run_version is None:
                raise RuntimeError("site update execution state disappeared")
            saved_update = update_repo.save(
                update.model_copy(
                    update={
                        "processing_status": ProcessingStatus.WAITING_FOR_APPROVAL,
                        "updated_at": now,
                    }
                ),
                expected_version=update_version,
            )
            run_repo.save(
                run.model_copy(
                    update={
                        "status": AgentRunStatus.WAITING_FOR_APPROVAL,
                        "step": step,
                        "result_summary": result_summary,
                        "pending_actions": list(pending_actions),
                    }
                ),
                expected_version=run_version,
            )
            return saved_update

        return self._transition(
            access,
            update_id,
            source_event_id=source_event_id,
            run_id=run_id,
            attempt=attempt,
            idempotency_key=f"site-update:{update_id}:approval",
            action="site_update.approval_requested",
            summary="Site update requires manager approval.",
            target=ProcessingStatus.WAITING_FOR_APPROVAL,
            mutation=mutation,
        )

    def fail(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        attempt: int,
        error_code: str,
        error_summary: str,
    ) -> SiteUpdateExecutionState:
        def mutation(session: RepositorySession, now: datetime) -> SiteUpdate:
            return self._finish(
                session,
                access,
                update_id,
                source_event_id=source_event_id,
                run_id=run_id,
                trace_id=trace_id,
                update_status=ProcessingStatus.FAILED,
                run_status=AgentRunStatus.FAILED,
                now=now,
                error_code=error_code,
                error_summary=error_summary,
            )

        return self._transition(
            access,
            update_id,
            source_event_id=source_event_id,
            run_id=run_id,
            attempt=attempt,
            idempotency_key=f"site-update:{update_id}:failed:{attempt}",
            action="site_update.processing_failed",
            summary="Site update processing failed and will be retried.",
            target=ProcessingStatus.FAILED,
            mutation=mutation,
        )

    def _finish(
        self,
        session: RepositorySession,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        trace_id: str,
        update_status: ProcessingStatus,
        run_status: AgentRunStatus,
        now: datetime,
        error_code: str | None = None,
        error_summary: str | None = None,
        result_summary: str | None = None,
        pending_actions: Sequence[str] = (),
    ) -> SiteUpdate:
        update_repo = session.repository(SiteUpdate)
        run_repo = session.repository(AgentRun)
        update = update_repo.require(access.project_id, update_id)
        run = run_repo.require(access.project_id, run_id)
        self._validate_run_contract(run, source_event_id, trace_id)
        if update.processing_status is not ProcessingStatus.PROCESSING:
            raise InvalidSiteUpdateTransition(
                f"cannot finish processing from {update.processing_status}"
            )
        if run.status is not AgentRunStatus.RUNNING:
            raise InvalidSiteUpdateTransition(f"cannot finish run from {run.status}")
        update_version = update_repo.version_of(access.project_id, update_id)
        run_version = run_repo.version_of(access.project_id, run_id)
        if update_version is None or run_version is None:
            raise RuntimeError("site update execution state disappeared")
        saved_update = update_repo.save(
            update.model_copy(
                update={
                    "processing_status": update_status,
                    "processed_at": now,
                    "updated_at": now,
                }
            ),
            expected_version=update_version,
        )
        run_repo.save(
            run.model_copy(
                update={
                    "status": run_status,
                    "completed_at": now,
                    "result_summary": result_summary,
                    "pending_actions": list(pending_actions),
                    "error_code": error_code,
                    "error_summary": error_summary,
                }
            ),
            expected_version=run_version,
        )
        return saved_update

    def _transition(
        self,
        access: ProjectAccessContext,
        update_id: str,
        *,
        source_event_id: str,
        run_id: str,
        attempt: int,
        idempotency_key: str,
        action: str,
        summary: str,
        target: ProcessingStatus,
        mutation: TransitionMutation,
    ) -> SiteUpdateExecutionState:
        now = datetime.now(UTC)
        context = MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            source_event_id=source_event_id,
            agent_run_id=run_id,
            idempotency_key=idempotency_key,
            occurred_at=now,
        )
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action=action,
                entity_type="site_update",
                entity_id=update_id,
                summary=summary,
                metadata={"processing_status": target.value, "attempt": attempt},
            ),
            lambda session: mutation(session, now),
            replay=lambda session, _activity: session.repository(SiteUpdate).require(
                access.project_id, update_id
            ),
        )
        if result.value is None:
            raise RuntimeError("site update transition replay did not resolve persisted state")
        return SiteUpdateExecutionState(
            update=result.value,
            run=self._store.repository(AgentRun).require(access.project_id, run_id),
        )

    @staticmethod
    def _validate_run_contract(run: AgentRun, source_event_id: str, trace_id: str) -> None:
        if (
            run.trigger_event_id != source_event_id
            or run.workflow is not WorkflowName.DAILY_SITE_UPDATE
            or run.trace_id != trace_id
        ):
            raise InvalidSiteUpdateTransition("agent run does not match site update event")


__all__ = [
    "InvalidSiteUpdateTransition",
    "SiteUpdateExecutionState",
    "SiteUpdateExecutionStateService",
]
