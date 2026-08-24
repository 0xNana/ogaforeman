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
    SiteUpdateWorkflowHandlers,
    build_site_update_app,
    managed_session_service,
    session_app_name,
    sqlite_session_execution_guard,
)
from app.agents.telemetry import run_adk_stage
from app.agents.identifiers import AdkAgentId, AdkNodeId, AdkToolId, AdkWorkflowId
from app.domain.enums import ActorType, AgentRunStatus, AttachmentUploadStatus, ProcessingStatus
from app.domain.events import EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    AgentRun,
    Approval,
    Attachment,
    MaterialRequest,
    OutboxMessage,
    ProjectMember,
    SiteUpdate,
)
from app.infrastructure.storage import StorageAdapter, create_storage_adapter
from app.repositories.context import ContextRepository
from app.repositories.interfaces import RepositoryStore
from app.services.context import ContextService
from app.services.issues import IssueService
from app.services.material_requests import MaterialRequestService
from app.services.materials import MaterialService
from app.services.reports import ReportService
from app.services.schedule_impact import calculate_impact
from app.services.site_update_lifecycle import SiteUpdateExecutionStateService
from app.services.site_updates import PreparedSiteUpdate, SiteUpdateResult, SiteUpdateService
from app.services.tasks import TaskService
from app.services.workflow_audit import WorkflowAuditService
from app.tools.materials import MaterialTools
from app.tools.tasks import TaskTools
from app.workflows.resume import ApprovalContinuationService
from app.repositories.runs import run_id_for_event


logger = logging.getLogger("ogaforeman.agents.site_update")


class EventPayloadMismatchError(ValueError):
    code = "EVENT_PAYLOAD_MISMATCH"


class SiteUpdateEventExecutor:
    def __init__(
        self,
        store: RepositoryStore,
        interpreter: SiteInterpreter | None,
        settings: Settings,
        storage_adapter: StorageAdapter | None = None,
    ) -> None:
        self._store = store
        self._interpreter = interpreter
        self._settings = settings
        self._storage = storage_adapter
        self._state = SiteUpdateExecutionStateService(store)

    async def execute(self, event: ProjectEvent, *, claim_attempt: int) -> dict[str, Any]:
        interpreter = self._require_interpreter()
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

        workflow_failure: list[Exception] = []
        staged_update = update
        staged_images: tuple[MediaEvidence, ...] = ()
        staged_context: Any = None
        staged_prepared: PreparedSiteUpdate | None = None
        staged_resolutions: dict[str, Any] = {}
        staged_branch_results: dict[str, dict[str, Any]] = {}
        staged_result: SiteUpdateResult | None = None
        staged_output: dict[str, Any] | None = None
        service = SiteUpdateService(
            interpreter=interpreter,
            context_service=ContextService(ContextRepository(self._store)),
            task_tools=TaskTools(TaskService(self._store), access),
            material_tools=MaterialTools(MaterialService(self._store), access),
            issue_service=IssueService(self._store),
            material_request_service=MaterialRequestService(self._store),
            report_service=ReportService(self._store),
            workflow_audit=WorkflowAuditService(self._store),
        )

        async def receive_input() -> dict[str, Any]:
            nonlocal staged_update
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
                adk_workflow_id=AdkWorkflowId.DAILY_SITE_UPDATE,
            )
            staged_update = started.update
            return {"update_id": staged_update.id, "run_id": run_id}

        async def prepare_evidence() -> dict[str, Any]:
            nonlocal staged_update, staged_images
            staged_update, images = await self._prepare_media(
                staged_update,
                access=access,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=trace_id,
            )
            staged_images = tuple(images)
            self._record_media_processed(
                staged_update,
                staged_images,
                source_event_id=event.event_id,
                run_id=run_id,
                attempt=claim_attempt,
            )
            return {
                "attachment_count": len(staged_images),
                "transcript_present": bool(staged_update.transcript),
            }

        async def retrieve_context() -> dict[str, Any]:
            nonlocal staged_context
            staged_context = service.retrieve_authorized_context(access)
            return {
                "project_id": staged_context.project_id,
                "task_count": len(staged_context.active_tasks),
                "material_count": len(staged_context.materials),
                "issue_count": len(staged_context.open_issues),
            }

        async def interpret_evidence() -> dict[str, Any]:
            nonlocal staged_prepared
            if staged_context is None:
                raise RuntimeError("site update context stage did not complete")
            staged_prepared = await service.interpret_evidence(
                staged_update,
                staged_context,
                images=staged_images,
            )
            facts = staged_prepared.fact_set
            return {
                "task_fact_count": len(facts.tasks),
                "issue_fact_count": len(facts.issues),
                "material_fact_count": len(facts.materials),
                "next_focus_fact_count": len(facts.next_focus),
                "safety_fact_count": len(facts.safety_issues),
            }

        async def resolve_entities() -> dict[str, Any]:
            nonlocal staged_resolutions
            if staged_prepared is None:
                raise RuntimeError("site update interpretation stage did not complete")
            staged_resolutions = service.resolve_canonical_entities(staged_prepared)
            return staged_resolutions

        async def analyze_progress() -> dict[str, Any]:
            if staged_prepared is None:
                raise RuntimeError("site update resolution stage did not complete")
            resolution = dict(staged_resolutions.get("progress", {}))
            result = {
                **resolution,
                "completion_fact_count": sum(
                    fact.is_completed for fact in staged_prepared.routed.actionable_tasks
                ),
                "unique_task_ids": sorted(set(resolution.get("resolved_ids", []))),
                "next_focus_task_ids": staged_resolutions.get("next_focus", {}).get(
                    "resolved_task_ids", []
                ),
            }
            staged_branch_results["progress"] = result
            return result

        async def analyze_blockers() -> dict[str, Any]:
            if staged_prepared is None:
                raise RuntimeError("site update resolution stage did not complete")
            resolution = dict(staged_resolutions.get("blockers", {}))
            blocked_ids = list(resolution.get("resolved_task_ids", []))
            impacted_ids = (
                sorted(calculate_impact(staged_prepared.project_context.active_tasks, blocked_ids))
                if blocked_ids
                else []
            )
            result = {
                **resolution,
                "issue_fact_count": len(staged_prepared.routed.actionable_issues),
                "impacted_task_ids": impacted_ids,
            }
            staged_branch_results["blockers"] = result
            return result

        async def analyze_materials() -> dict[str, Any]:
            if staged_prepared is None:
                raise RuntimeError("site update resolution stage did not complete")
            resolution = dict(staged_resolutions.get("materials", {}))
            quantities = [
                fact.quantity
                for fact in staged_prepared.routed.actionable_materials
                if fact.quantity is not None and fact.quantity >= 0
            ]
            result = {
                **resolution,
                "stock_observation_count": len(quantities),
                "invalid_quantity_count": sum(
                    fact.quantity is None or fact.quantity < 0
                    for fact in staged_prepared.routed.actionable_materials
                ),
            }
            staged_branch_results["materials"] = result
            return result

        async def merge_results() -> dict[str, Any]:
            missing = {"progress", "blockers", "materials"} - set(staged_branch_results)
            if missing:
                raise RuntimeError(f"site update merge is missing branches: {sorted(missing)}")
            return {
                "progress": staged_branch_results["progress"],
                "blockers": staged_branch_results["blockers"],
                "materials": staged_branch_results["materials"],
                "next_focus": staged_resolutions.get("next_focus", {}),
            }

        async def apply_policy() -> dict[str, Any]:
            if staged_prepared is None:
                raise RuntimeError("site update interpretation stage did not complete")
            return {
                "safety_stop": bool(staged_prepared.routed.safety_stops),
                "clarification_count": (
                    len(staged_prepared.routed.clarifications)
                    + sum(
                        int(branch.get("unresolved_count", 0))
                        + int(branch.get("ambiguous_count", 0))
                        for branch in staged_branch_results.values()
                    )
                ),
                "autonomous_mutations_allowed": not bool(staged_prepared.routed.safety_stops),
            }

        async def invoke_typed_tools() -> dict[str, Any]:
            nonlocal staged_result, staged_output
            if staged_prepared is None:
                raise RuntimeError("site update preparation did not complete")
            result = await service.process_update(
                access=access,
                site_update=staged_update,
                run_id=run_id,
                trace_id=trace_id,
                source_event_id=event.event_id,
                images=staged_images,
                attempt=claim_attempt,
                prepared=staged_prepared,
            )
            staged_result = result
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

            staged_output = {
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
            return staged_output

        async def project_daily_log() -> dict[str, Any]:
            if staged_result is None:
                raise RuntimeError("site update tools did not produce a report")
            return {"report_id": staged_result.report_id}

        async def emit_activity() -> dict[str, Any]:
            if staged_result is None:
                raise RuntimeError("site update tools did not produce activity")
            return {
                "tasks_updated": staged_result.tasks_updated,
                "materials_updated": staged_result.materials_updated,
                "issues_created": staged_result.issues_created,
            }

        async def complete_stage() -> dict[str, Any]:
            return staged_output or {}

        def guarded(stage: Any, node: str, *, tool: str | None = None) -> Any:
            async def run() -> dict[str, Any]:
                try:
                    return await run_adk_stage(
                        logger,
                        workflow=AdkWorkflowId.DAILY_SITE_UPDATE,
                        agent=AdkAgentId.DAILY_SITE_UPDATE,
                        node=node,
                        tool=tool,
                        execute=stage,
                    )
                except Exception as exc:
                    workflow_failure.append(exc)
                    raise

            return run

        handlers = SiteUpdateWorkflowHandlers(
            receive_input=guarded(receive_input, AdkNodeId.RECEIVE_INPUT),
            prepare_evidence=guarded(prepare_evidence, AdkNodeId.PREPARE_MULTIMODAL_INPUT),
            retrieve_context=guarded(retrieve_context, AdkNodeId.RETRIEVE_AUTHORIZED_CONTEXT),
            interpret_evidence=guarded(interpret_evidence, AdkNodeId.INTERPRET_EVIDENCE),
            resolve_entities=guarded(resolve_entities, AdkNodeId.RESOLVE_CANONICAL_ENTITIES),
            analyze_progress=guarded(analyze_progress, AdkNodeId.PROGRESS),
            analyze_blockers=guarded(analyze_blockers, AdkNodeId.BLOCKER),
            analyze_materials=guarded(analyze_materials, AdkNodeId.MATERIAL),
            merge_results=guarded(merge_results, AdkNodeId.MERGE_ACTIONS),
            apply_policy=guarded(apply_policy, AdkNodeId.EVALUATE_POLICY),
            invoke_typed_tools=guarded(
                invoke_typed_tools,
                AdkNodeId.EXECUTE_SITE_UPDATE,
                tool=AdkToolId.SITE_UPDATE_TOOLS,
            ),
            project_daily_log=guarded(project_daily_log, AdkNodeId.PROJECT_DAILY_LOG),
            emit_activity=guarded(emit_activity, AdkNodeId.EMIT_ACTIVITY),
            complete=guarded(complete_stage, AdkNodeId.FINALIZE_SITE_UPDATE),
        )

        app = build_site_update_app(
            adk_app_name,
            handlers=handlers,
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
            failure = workflow_failure[0] if workflow_failure else exc
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

    async def resume_approved(self, event: ProjectEvent) -> dict[str, Any]:
        """Resume the persisted Daily Site Update ADK invocation after approval."""

        _original_event, update, access, run = self._load_approved_site_update(event)
        if (
            update.processing_status is ProcessingStatus.COMPLETED
            and run.status is AgentRunStatus.COMPLETED
        ):
            return {
                **_completed_output(_original_event, update, run, replayed=True),
                "result_ref": f"run:{run.id}",
            }
        persisted_session = run.adk_session_id
        if not persisted_session or not run.adk_invocation_id:
            raise RuntimeError("approval run is missing its persisted ADK invocation")
        if run.adk_workflow_id != AdkWorkflowId.DAILY_SITE_UPDATE:
            raise RuntimeError("approval run does not reference the Daily Site Update workflow")

        stored_app_name, separator, session_id = persisted_session.partition("/")
        if not separator or not stored_app_name or not session_id:
            raise RuntimeError("approval run has an invalid persisted ADK session identity")

        workflow_failure: list[Exception] = []

        async def continue_after_approval() -> dict[str, Any]:
            try:
                continuation = ApprovalContinuationService(self._store).handle_approval_granted(
                    event.project_id,
                    str(event.payload["approval_id"]),
                    str(event.payload["resolver"]),
                    source_event_id=event.event_id,
                    occurred_at=event.occurred_at,
                )
                return {
                    "status": "completed",
                    "update_id": update.id,
                    "run_id": continuation.run_id,
                    "result_ref": f"run:{continuation.run_id}",
                    "has_safety_stops": False,
                    "has_clarifications": False,
                    "has_pending_approvals": False,
                    "summary": run.result_summary or "Approved material workflow completed.",
                    "pending_actions": [],
                    "replayed": False,
                }
            except Exception as exc:
                workflow_failure.append(exc)
                return {"status": "failed", "_adk_failure": True}

        app = build_site_update_app(
            stored_app_name,
            continue_after_approval,
            timeout_seconds=self._settings.agent_workflow_timeout_seconds,
        )
        output: dict[str, Any] | None = None
        async with (
            managed_session_service(self._settings) as session_service,
            sqlite_session_execution_guard(self._settings),
            asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
        ):
            session = await session_service.get_session(
                app_name=stored_app_name,
                user_id=access.actor.user_id,
                session_id=session_id,
            )
            if session is None:
                raise RuntimeError(
                    "approval ADK session was not found after restart "
                    f"(app_name={stored_app_name}, session_id={session_id})"
                )
            call_id = next(
                (
                    part.function_call.id
                    for history_event in session.events
                    if history_event.content and history_event.content.parts
                    for part in history_event.content.parts
                    if part.function_call and part.function_call.name == "adk_request_input"
                ),
                None,
            )
            if call_id is None:
                raise RuntimeError("approval ADK request input was not persisted")
            output = next(
                (
                    getattr(history_event, "output", None)
                    for history_event in reversed(session.events)
                    if isinstance(getattr(history_event, "output", None), dict)
                    and getattr(history_event, "output").get("status") == "completed"
                    and getattr(history_event, "output").get("run_id") == run.id
                    and getattr(history_event, "output").get("update_id") == update.id
                ),
                None,
            )
            if output is None:
                runner = Runner(app=app, session_service=session_service)
                async for agent_event in runner.run_async(
                    user_id=access.actor.user_id,
                    session_id=session_id,
                    invocation_id=run.adk_invocation_id,
                    new_message=types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    id=call_id,
                                    name="adk_request_input",
                                    response={
                                        "approval": "approved",
                                        "approval_id": str(event.payload["approval_id"]),
                                    },
                                )
                            )
                        ],
                    ),
                ):
                    if isinstance(agent_event.output, dict):
                        output = agent_event.output
        if workflow_failure:
            raise workflow_failure[0]
        if output is None:
            raise RuntimeError("approved Daily Site Update ADK workflow returned no result")
        if output.get("run_id") != run.id or output.get("update_id") != update.id:
            raise RuntimeError("approved ADK workflow returned mismatched persisted identity")
        ApprovalContinuationService(self._store).complete_approved_material_workflow(
            event.project_id,
            str(event.payload["approval_id"]),
            str(event.payload["resolver"]),
            source_event_id=event.event_id,
        )
        return output

    def _load_approved_site_update(
        self,
        event: ProjectEvent,
    ) -> tuple[ProjectEvent, SiteUpdate, ProjectAccessContext, AgentRun]:
        if event.event_type is not EventType.APPROVAL_GRANTED:
            raise ValueError("site-update approval resume requires APPROVAL_GRANTED")
        approval_id = str(event.payload["approval_id"])
        self._store.repository(Approval).require(event.project_id, approval_id)
        requests = [
            request
            for request in self._store.repository(MaterialRequest).list(event.project_id)
            if request.approval_id == approval_id
        ]
        if len(requests) != 1:
            raise RuntimeError("approval must be linked to exactly one material request")
        run = self._store.repository(AgentRun).require(
            event.project_id,
            run_id_for_event(requests[0].source_event_id),
        )
        source_messages = [
            message
            for message in self._store.repository(OutboxMessage).list(event.project_id)
            if message.message_type == EventType.SITE_UPDATE_RECEIVED.value
            and message.payload.get("event_id") == run.trigger_event_id
        ]
        if len(source_messages) != 1:
            raise RuntimeError("original site-update event was not persisted exactly once")
        original_event = ProjectEvent.model_validate(source_messages[0].payload)
        update, access, authorized_run = self._load_authorized_state(original_event)
        if authorized_run.id != run.id:
            raise RuntimeError("approval does not reference the original site-update run")
        valid_state_pairs = {
            (ProcessingStatus.WAITING_FOR_APPROVAL, AgentRunStatus.WAITING_FOR_APPROVAL),
            (ProcessingStatus.PROCESSING, AgentRunStatus.RUNNING),
            (ProcessingStatus.COMPLETED, AgentRunStatus.COMPLETED),
        }
        if (update.processing_status, run.status) not in valid_state_pairs:
            raise RuntimeError("site-update workflow is not paused for approval")
        return original_event, update, access, run

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
                transcript_parts.append(await self._require_interpreter().transcribe_audio(audio))
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

    def _require_interpreter(self) -> SiteInterpreter:
        if self._interpreter is None:
            raise RuntimeError("site update execution requires an interpreter")
        return self._interpreter

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
