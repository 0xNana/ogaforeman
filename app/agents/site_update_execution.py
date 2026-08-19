"""ADK execution bridge for persisted Daily Site Update events."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from google.adk.runners import Runner
from google.genai import types

from app.agents.interpreter import SiteInterpreter
from app.config.settings import Settings
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectPermission,
    authorize_project_member,
)
from app.domain.activity import MutationContext, WorkflowActivityAction
from app.agents.interpreter import MediaEvidence
from app.agents.adk_runtime import (
    build_site_update_app,
    managed_session_service,
    session_app_name,
    sqlite_session_execution_guard,
)
from app.domain.enums import ActorType, AgentRunStatus, AttachmentUploadStatus, ProcessingStatus
from app.domain.events import EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import AgentRun, Attachment, ProjectMember, SiteUpdate
from app.infrastructure.storage import StorageAdapter, create_storage_adapter
from app.repositories.context import ContextRepository
from app.repositories.interfaces import RepositoryStore
from app.services.context import ContextService
from app.services.issues import IssueService
from app.services.material_requests import MaterialRequestService
from app.services.materials import MaterialService
from app.services.reports import ReportService
from app.services.site_update_lifecycle import SiteUpdateExecutionStateService
from app.services.site_updates import SiteUpdateService
from app.services.tasks import TaskService
from app.services.workflow_audit import WorkflowAuditService
from app.tools.materials import MaterialTools
from app.tools.tasks import TaskTools
from app.repositories.runs import run_id_for_event


logger = logging.getLogger("ogaforeman.agents.site_update")


class EventPayloadMismatchError(ValueError):
    code = "EVENT_PAYLOAD_MISMATCH"


class SiteUpdateEventExecutor:
    def __init__(
        self,
        store: RepositoryStore,
        interpreter: SiteInterpreter,
        settings: Settings,
        storage_adapter: StorageAdapter | None = None,
    ) -> None:
        self._store = store
        self._interpreter = interpreter
        self._settings = settings
        self._storage = storage_adapter
        self._state = SiteUpdateExecutionStateService(store)

    async def execute(self, event: ProjectEvent, *, claim_attempt: int) -> dict[str, Any]:
        update, access, run = self._load_authorized_state(event)
        if (
            update.processing_status is ProcessingStatus.COMPLETED
            and run.status is AgentRunStatus.COMPLETED
        ):
            return _completed_output(event, update, run, replayed=True)
        if (
            update.processing_status is ProcessingStatus.WAITING_FOR_CLARIFICATION
            and run.status is AgentRunStatus.WAITING_FOR_CLARIFICATION
        ):
            return _paused_output(event, update, run, replayed=True)
        if (
            update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
            and run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        ):
            return _paused_output(event, update, run, replayed=True)
        if update.processing_status in {
            ProcessingStatus.COMPLETED,
            ProcessingStatus.WAITING_FOR_APPROVAL,
            ProcessingStatus.WAITING_FOR_CLARIFICATION,
        } or run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.WAITING_FOR_APPROVAL,
            AgentRunStatus.WAITING_FOR_CLARIFICATION,
        }:
            raise EventPayloadMismatchError("site update and agent run terminal states disagree")

        run_id = run.id
        trace_id = run.trace_id
        adk_app_name = session_app_name(self._settings, self._store)
        adk_session_id = f"{run_id}-attempt-{claim_attempt}"

        async def workflow() -> dict[str, Any]:
            started = self._state.start_attempt(
                access,
                update.id,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=trace_id,
                attempt=claim_attempt,
                # Persist the namespace together with the session cursor so a
                # restarted worker can find the exact ADK session even when a
                # local/test repository object is reconstructed.
                adk_session_id=f"{adk_app_name}/{adk_session_id}",
                adk_invocation_id=event.event_id,
                adk_workflow_id="daily_site_update_workflow",
            )
            enriched_update, images = await self._prepare_media(
                started.update,
                access=access,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=trace_id,
            )
            self._record_media_processed(
                enriched_update,
                images,
                source_event_id=event.event_id,
                run_id=run_id,
                attempt=claim_attempt,
            )
            service = SiteUpdateService(
                interpreter=self._interpreter,
                context_service=ContextService(ContextRepository(self._store)),
                task_tools=TaskTools(TaskService(self._store), access),
                material_tools=MaterialTools(MaterialService(self._store), access),
                issue_service=IssueService(self._store),
                material_request_service=MaterialRequestService(self._store),
                report_service=ReportService(self._store),
                workflow_audit=WorkflowAuditService(self._store),
            )
            result = await service.process_update(
                access=access,
                site_update=enriched_update,
                run_id=run_id,
                trace_id=trace_id,
                source_event_id=event.event_id,
                images=images,
                attempt=claim_attempt,
            )
            if result.has_safety_stops or result.has_clarifications:
                final = self._state.wait_for_clarification(
                    access,
                    update.id,
                    source_event_id=event.event_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    attempt=claim_attempt,
                    step="safety_stop" if result.has_safety_stops else "clarification_needed",
                    result_summary=result.summary,
                    pending_actions=result.pending_actions,
                )
                status = "paused"
            elif result.has_pending_approvals:
                final = self._state.wait_for_approval(
                    access,
                    update.id,
                    source_event_id=event.event_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    attempt=claim_attempt,
                    step="approval_required",
                    result_summary=result.summary,
                    pending_actions=result.pending_actions,
                )
                status = "paused"
            else:
                final = self._state.complete(
                    access,
                    update.id,
                    source_event_id=event.event_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    attempt=claim_attempt,
                    result_summary=result.summary,
                    pending_actions=result.pending_actions,
                )
                status = "completed"

            return {
                "status": status,
                "update_id": update.id,
                "run_id": final.run.id,
                "tasks_updated": result.tasks_updated,
                "materials_updated": result.materials_updated,
                "issues_created": result.issues_created,
                "material_requests_created": result.material_requests_created,
                "approvals_requested": result.approvals_requested,
                "report_id": result.report_id,
                "has_safety_stops": result.has_safety_stops,
                "has_clarifications": result.has_clarifications,
                "has_pending_approvals": result.has_pending_approvals,
                "summary": result.summary,
                "pending_actions": list(result.pending_actions),
                "replayed": False,
            }

        workflow_failure: list[Exception] = []

        async def adk_execute() -> dict[str, Any]:
            try:
                return await workflow()
            except Exception as exc:
                # ADK 2.6.2's graph scheduler converts child exceptions into a
                # node timeout while draining the graph. Preserve the original
                # domain exception for the worker's retry/error contract.
                workflow_failure.append(exc)
                return {"status": "failed", "_adk_failure": True}

        app = build_site_update_app(
            adk_app_name,
            adk_execute,
            timeout_seconds=self._settings.agent_workflow_timeout_seconds,
        )
        output: dict[str, Any] | None = None
        try:
            async with (
                managed_session_service(self._settings) as session_service,
                sqlite_session_execution_guard(self._settings),
                asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
            ):
                runner = Runner(
                    # Scope the ADK session namespace to the canonical run. This keeps
                    # independent project runs isolated while allowing retries to
                    # resume the exact same ADK session.
                    app=app,
                    session_service=session_service,
                    auto_create_session=True,
                )
                async for agent_event in runner.run_async(
                    user_id=access.actor.user_id,
                    session_id=adk_session_id,
                    invocation_id=event.event_id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part(text=f"Process persisted site update {update.id}.")],
                    ),
                ):
                    if agent_event.output is not None:
                        from google.adk.events import RequestInput

                        if isinstance(agent_event.output, RequestInput):
                            output = agent_event.output.payload
                        elif not isinstance(agent_event.output, dict):
                            raise RuntimeError("site update agent returned an invalid output")
                        else:
                            output = agent_event.output
                    elif agent_event.content and agent_event.content.parts:
                        # Workflow converts RequestInput into an ADK function
                        # call event rather than exposing the RequestInput
                        # object directly through Event.output.
                        for part in agent_event.content.parts:
                            call = part.function_call
                            if call and call.name == "adk_request_input":
                                output = (call.args or {}).get("payload")
                                break
        except Exception as exc:
            self._record_failure(
                event,
                access,
                update.id,
                run_id,
                trace_id,
                claim_attempt,
                exc,
            )
            raise
        if output is None:
            error = RuntimeError("site update agent completed without an output")
            self._record_failure(
                event,
                access,
                update.id,
                run_id,
                trace_id,
                claim_attempt,
                error,
            )
            raise error
        if workflow_failure:
            failure = workflow_failure[0]
            self._record_failure(
                event,
                access,
                update.id,
                run_id,
                trace_id,
                claim_attempt,
                failure,
            )
            raise failure
        return output

    async def _prepare_media(
        self,
        update: SiteUpdate,
        *,
        access: ProjectAccessContext,
        source_event_id: str,
        run_id: str,
        trace_id: str,
    ) -> tuple[SiteUpdate, tuple[MediaEvidence, ...]]:
        attachments = self._store.repository(Attachment)
        media_attachments: list[Attachment] = []
        for attachment_id in update.attachment_ids:
            attachment = attachments.require(update.project_id, attachment_id)
            if (
                attachment.upload_status is not AttachmentUploadStatus.VERIFIED
                or attachment.site_update_id != update.id
            ):
                raise EventPayloadMismatchError(
                    "site update media is not a verified linked attachment"
                )
            if attachment.content_type.startswith(("audio/", "image/")):
                media_attachments.append(attachment)
        if not media_attachments:
            return update, ()

        storage = self._storage or create_storage_adapter(self._settings)
        total_bytes = 0
        images: list[MediaEvidence] = []
        audio_parts: list[MediaEvidence] = []
        already_transcribed = set(update.transcribed_attachment_ids)
        for attachment in media_attachments:
            if (
                attachment.content_type.startswith("audio/")
                and attachment.id in already_transcribed
            ):
                continue
            remaining = self._settings.max_model_media_bytes - total_bytes
            if remaining <= 0:
                raise ValueError("site update media exceeds the model input limit")
            data = await asyncio.to_thread(
                storage.read_bytes,
                object_path=attachment.object_path,
                expected_sha256=attachment.sha256,
                max_bytes=remaining,
            )
            if len(data) != attachment.byte_size:
                raise ValueError("stored media size changed after attachment verification")
            total_bytes += len(data)
            media = MediaEvidence(
                attachment_id=attachment.id,
                content_type=attachment.content_type,
                data=data,
            )
            if attachment.content_type.startswith("audio/"):
                audio_parts.append(media)
            else:
                images.append(media)

        if audio_parts:
            transcript_parts = [update.transcript] if update.transcript else []
            for audio in audio_parts:
                transcript_parts.append(await self._interpreter.transcribe_audio(audio))
            transcript = "\n".join(part.strip() for part in transcript_parts if part.strip())
            if len(transcript) > self._settings.max_event_text_chars:
                raise ValueError("voice transcription exceeds the model text input limit")
            transcribed_ids = [
                *update.transcribed_attachment_ids,
                *(audio.attachment_id for audio in audio_parts),
            ]
            update = self._state.persist_transcript(
                access,
                update.id,
                source_event_id=source_event_id,
                run_id=run_id,
                trace_id=trace_id,
                transcript=transcript,
                attachment_ids=transcribed_ids,
            )
        return update, tuple(images)

    def _record_media_processed(
        self,
        update: SiteUpdate,
        images: tuple[MediaEvidence, ...],
        *,
        source_event_id: str,
        run_id: str,
        attempt: int,
    ) -> None:
        audio_ids = list(update.transcribed_attachment_ids)
        image_ids = [image.attachment_id for image in images]
        WorkflowAuditService(self._store).record(
            MutationContext(
                project_id=update.project_id,
                actor_type=ActorType.SYSTEM,
                source_event_id=source_event_id,
                agent_run_id=run_id,
                idempotency_key=(f"workflow-audit:{update.id}:media-processed:{attempt}"),
                occurred_at=datetime.now(UTC),
            ),
            action=WorkflowActivityAction.SITE_UPDATE_MEDIA_PROCESSED,
            entity_type="site_update",
            entity_id=update.id,
            summary="Processed the site update's linked media for interpretation.",
            metadata={
                "status": "processed" if audio_ids or image_ids else "not_applicable",
                "attempt": attempt,
                "media_attachment_count": len(audio_ids) + len(image_ids),
                "audio_attachment_count": len(audio_ids),
                "image_attachment_count": len(image_ids),
                "audio_attachment_ids": audio_ids,
                "image_attachment_ids": image_ids,
                "transcribed_attachment_ids": update.transcribed_attachment_ids,
            },
        )

    def _load_authorized_state(
        self,
        event: ProjectEvent,
    ) -> tuple[SiteUpdate, ProjectAccessContext, AgentRun]:
        if event.event_type is not EventType.SITE_UPDATE_RECEIVED:
            raise ValueError("site update executor received an unsupported event")
        update_id = str(event.payload["site_update_id"])
        update = self._store.repository(SiteUpdate).require(event.project_id, update_id)
        submitted_transcript = update.submitted_transcript
        if submitted_transcript is None and not update.transcribed_attachment_ids:
            submitted_transcript = update.transcript
        expected_payload = {
            "site_update_id": update.id,
            "text": update.raw_text,
            "transcript": submitted_transcript,
            "attachment_ids": update.attachment_ids,
        }
        delivered_payload = {
            "site_update_id": event.payload.get("site_update_id"),
            "text": event.payload.get("text"),
            "transcript": event.payload.get("transcript"),
            "attachment_ids": list(event.payload.get("attachment_ids", [])),
        }
        if (
            event.source is not EventSource.WEB
            or event.actor.type is not EventActorType.USER
            or event.actor.id != update.submitted_by
            or event.occurred_at != update.submitted_at
            or delivered_payload != expected_payload
        ):
            raise EventPayloadMismatchError(
                "site update event does not match its persisted authorized source"
            )
        actor = AuthenticatedUser(
            user_id=event.actor.id,
            subject="persisted-site-update-event",
        )
        membership = self._store.repository(ProjectMember).get(
            event.project_id,
            event.actor.id,
        )
        access = authorize_project_member(
            actor,
            event.project_id,
            membership,
            ProjectPermission.OPERATE,
        )
        run = self._store.repository(AgentRun).require(
            event.project_id,
            run_id_for_event(event.event_id),
        )
        return update, access, run

    def _record_failure(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        update_id: str,
        run_id: str,
        trace_id: str,
        attempt: int,
        error: Exception,
    ) -> None:
        run = self._store.repository(AgentRun).require(event.project_id, run_id)
        update = self._store.repository(SiteUpdate).require(event.project_id, update_id)
        if (
            run.status is not AgentRunStatus.RUNNING
            or update.processing_status is not ProcessingStatus.PROCESSING
        ):
            return
        error_code = type(error).__name__[:128]
        try:
            self._state.fail(
                access,
                update_id,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=trace_id,
                attempt=attempt,
                error_code=error_code,
                error_summary=f"{error_code}: site update workflow execution failed",
            )
        except Exception:
            logger.exception("failed to persist site update workflow failure state")


def _completed_output(
    event: ProjectEvent,
    update: SiteUpdate,
    run: AgentRun,
    *,
    replayed: bool,
) -> dict[str, Any]:
    return {
        "status": "completed",
        "update_id": update.id,
        "run_id": run.id,
        "tasks_updated": 0,
        "materials_updated": 0,
        "issues_created": 0,
        "material_requests_created": 0,
        "approvals_requested": 0,
        "report_id": None,
        "has_safety_stops": False,
        "has_clarifications": False,
        "has_pending_approvals": False,
        "replayed": replayed,
        "event_id": event.event_id,
    }


def _paused_output(
    event: ProjectEvent,
    update: SiteUpdate,
    run: AgentRun,
    *,
    replayed: bool,
) -> dict[str, Any]:
    return {
        "status": "paused",
        "update_id": update.id,
        "run_id": run.id,
        "tasks_updated": 0,
        "materials_updated": 0,
        "issues_created": 0,
        "material_requests_created": 0,
        "approvals_requested": 0,
        "report_id": None,
        "has_safety_stops": False,
        "has_clarifications": run.status is AgentRunStatus.WAITING_FOR_CLARIFICATION,
        "has_pending_approvals": run.status is AgentRunStatus.WAITING_FOR_APPROVAL,
        "replayed": replayed,
        "event_id": event.event_id,
    }


__all__ = [
    "EventPayloadMismatchError",
    "SiteUpdateEventExecutor",
]
