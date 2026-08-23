"""ADK entrypoint for persisted non-site agentic events."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.apps import App, ResumabilityConfig
from google.adk.events import RequestInput
from google.adk.runners import Runner
from google.adk.workflow import FunctionNode, START, Workflow
from google.genai import types

from app.agents.adk_runtime import (
    managed_session_service,
    session_app_name,
    sqlite_session_execution_guard,
)
from app.agents.telemetry import run_adk_stage
from app.agents.identifiers import AdkAgentId, AdkNodeId, AdkToolId, AdkWorkflowId
from app.config.settings import NotificationProviderName, Settings
from app.domain.events import ProjectEvent
from app.domain.authorization import ProjectAccessContext
from app.repositories.interfaces import RepositoryStore
from app.infrastructure.google_chat import GoogleChatNotificationProvider
from app.infrastructure.logging_notification import LoggingNotificationProvider
from app.infrastructure.notification_gateway import NotificationProvider
from app.services.delivery_notifications import NotificationService
from app.services.routed_events import (
    DeliveryDelayAssessment,
    DeliveryDelayContext,
    RoutedEventExecution,
    TypedEventService,
)
from app.domain.models import Approval, MaterialRequest, AgentRun, Issue, SiteUpdate, Task
from app.domain.enums import WorkflowName
from app.workflows.resume import ApprovalContinuationService
from app.repositories.runs import run_id_for_event


logger = logging.getLogger("ogaforeman.agents.events")


def build_project_event_workflow(execute: Any, timeout_seconds: int) -> Workflow:
    async def run_event() -> dict[str, Any] | RequestInput:
        result = await execute()
        if result.get("waiting_for_approval"):
            return RequestInput(
                interrupt_id="approval_required",
                message="Approval is required to continue this workflow.",
                payload=result,
                response_schema=dict[str, Any],
            )
        return result

    node = FunctionNode(
        func=run_event,
        name="execute_event",
        rerun_on_resume=True,
        timeout=timeout_seconds,
    )
    return Workflow(name=AdkWorkflowId.PROJECT_EVENT, edges=[(START, node)])


def build_delivery_delay_workflow(handlers: dict[str, Any], timeout_seconds: int) -> Workflow:
    """Build the dedicated, auditable delivery-delay ADK graph."""

    def node(name: str) -> FunctionNode:
        return FunctionNode(func=handlers[name], name=name, timeout=timeout_seconds)

    receive = node(AdkNodeId.RECEIVE_DELIVERY_DELAY)
    context = node(AdkNodeId.RETRIEVE_REQUEST_CONTEXT)
    assess = node(AdkNodeId.ASSESS_DELIVERY_IMPACT)
    request_tool = node(AdkNodeId.MARK_REQUEST_DELAYED)
    risk_tool = node(AdkNodeId.CREATE_DELIVERY_RISK)
    follow_up_tool = node(AdkNodeId.CREATE_DELIVERY_FOLLOW_UP)
    notification_tool = node(AdkNodeId.DELIVER_DELIVERY_NOTIFICATION)
    complete = node(AdkNodeId.COMPLETE_DELIVERY_DELAY)
    return Workflow(
        name=AdkWorkflowId.DELIVERY_DELAY,
        edges=[
            (
                START,
                receive,
                context,
                assess,
                request_tool,
                risk_tool,
                follow_up_tool,
                notification_tool,
                complete,
            )
        ],
    )


class DeliveryDelayEventExecutor:
    """Run delivery-delay impact and follow-through as an ADK-owned workflow."""

    def __init__(
        self,
        store: RepositoryStore,
        settings: Settings,
        notification_provider: NotificationProvider | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._notification_provider = notification_provider

    async def execute(self, event: ProjectEvent) -> RoutedEventExecution:
        service = TypedEventService(self._store)
        access: ProjectAccessContext | None = None
        run_id: str | None = None
        context: DeliveryDelayContext | None = None
        assessment: DeliveryDelayAssessment | None = None
        issue: Issue | None = None
        follow_up: Task | None = None

        async def receive_delivery_delay() -> dict[str, Any]:
            nonlocal access, run_id
            access, run_id = service.start_delivery_delay(event)
            return {"run_id": run_id, "request_id": str(event.payload["request_id"])}

        async def retrieve_authorized_request_context() -> dict[str, Any]:
            nonlocal context
            if access is None:
                raise RuntimeError("delivery delay authorization stage did not complete")
            context = service.retrieve_delivery_delay_context(event, access)
            return {
                "project_id": event.project_id,
                "project_name": context.project.name,
                "request_id": context.request.id,
                "material_id": context.material.id,
                "directly_affected_task_ids": list(context.directly_affected_task_ids),
            }

        async def assess_material_schedule_impact() -> dict[str, Any]:
            nonlocal assessment
            if context is None:
                raise RuntimeError("delivery delay context stage did not complete")
            assessment = service.assess_delivery_delay(context)
            return {
                "affected_task_ids": list(assessment.affected_task_ids),
                "severity": assessment.severity.value,
            }

        async def mark_material_request_delayed_tool() -> dict[str, Any]:
            if access is None or run_id is None:
                raise RuntimeError("delivery delay run was not started")
            request = service.mark_delivery_delayed(event, access, run_id)
            return {"request_id": request.id, "status": request.status.value}

        async def create_delivery_risk_tool() -> dict[str, Any]:
            nonlocal issue
            if access is None or run_id is None or assessment is None:
                raise RuntimeError("delivery delay assessment stage did not complete")
            issue = service.create_delivery_delay_risk(event, access, run_id, assessment)
            return {"issue_id": issue.id, "affected_task_ids": issue.task_ids}

        async def create_delivery_follow_up_tool() -> dict[str, Any]:
            nonlocal follow_up
            if access is None or run_id is None or assessment is None or issue is None:
                raise RuntimeError("delivery delay risk stage did not complete")
            follow_up = service.create_delivery_delay_follow_up(
                event, access, run_id, assessment, issue
            )
            return {"follow_up_task_id": follow_up.id}

        async def deliver_delivery_notification_tool() -> dict[str, Any]:
            if run_id is None or context is None or assessment is None:
                raise RuntimeError("delivery delay impact stage did not complete")
            if issue is None or follow_up is None:
                raise RuntimeError("delivery delay follow-up stage did not complete")
            notification = await asyncio.to_thread(
                NotificationService(
                    self._store,
                    self._provider(),
                    max_attempts=self._settings.notification_max_attempts,
                    base_backoff_seconds=self._settings.notification_backoff_seconds,
                    claim_lease_seconds=self._settings.notification_claim_lease_seconds,
                    public_app_base_url=self._settings.public_app_base_url,
                ).deliver,
                event,
                run_id,
                context,
                assessment,
                issue,
                follow_up,
            )
            return {
                "outbox_item_id": notification.id,
                "provider": notification.provider,
                "delivery_status": notification.status.value,
                "provider_message_id": notification.provider_message_id,
            }

        async def complete_delivery_delay() -> dict[str, Any]:
            if run_id is None or issue is None:
                raise RuntimeError("delivery delay tools did not complete")
            result = service.complete_delivery_delay(event.project_id, run_id, issue.id)
            return {"run_id": result.run_id, "result_ref": result.result_ref}

        def observed(name: str, execute: Any, *, tool: str | None = None) -> Any:
            async def run() -> dict[str, Any]:
                return await run_adk_stage(
                    logger,
                    workflow=AdkWorkflowId.DELIVERY_DELAY,
                    agent=AdkAgentId.DELIVERY_DELAY,
                    node=name,
                    tool=tool,
                    execute=execute,
                )

            return run

        handlers: dict[str, Any] = {
            AdkNodeId.RECEIVE_DELIVERY_DELAY: observed(
                AdkNodeId.RECEIVE_DELIVERY_DELAY, receive_delivery_delay
            ),
            AdkNodeId.RETRIEVE_REQUEST_CONTEXT: observed(
                AdkNodeId.RETRIEVE_REQUEST_CONTEXT, retrieve_authorized_request_context
            ),
            AdkNodeId.ASSESS_DELIVERY_IMPACT: observed(
                AdkNodeId.ASSESS_DELIVERY_IMPACT, assess_material_schedule_impact
            ),
            AdkNodeId.MARK_REQUEST_DELAYED: observed(
                AdkNodeId.MARK_REQUEST_DELAYED,
                mark_material_request_delayed_tool,
                tool=AdkToolId.MARK_MATERIAL_REQUEST_DELAYED,
            ),
            AdkNodeId.CREATE_DELIVERY_RISK: observed(
                AdkNodeId.CREATE_DELIVERY_RISK,
                create_delivery_risk_tool,
                tool=AdkToolId.CREATE_ISSUE,
            ),
            AdkNodeId.CREATE_DELIVERY_FOLLOW_UP: observed(
                AdkNodeId.CREATE_DELIVERY_FOLLOW_UP,
                create_delivery_follow_up_tool,
                tool=AdkToolId.CREATE_DELIVERY_FOLLOW_UP,
            ),
            AdkNodeId.DELIVER_DELIVERY_NOTIFICATION: observed(
                AdkNodeId.DELIVER_DELIVERY_NOTIFICATION,
                deliver_delivery_notification_tool,
                tool=AdkToolId.SEND_DELIVERY_NOTIFICATION,
            ),
            AdkNodeId.COMPLETE_DELIVERY_DELAY: observed(
                AdkNodeId.COMPLETE_DELIVERY_DELAY, complete_delivery_delay
            ),
        }
        app_name = session_app_name(self._settings, self._store)
        app = App(
            name=app_name,
            root_agent=build_delivery_delay_workflow(
                handlers, self._settings.agent_workflow_timeout_seconds
            ),
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        result: RoutedEventExecution | None = None
        try:
            async with (
                managed_session_service(self._settings) as session_service,
                sqlite_session_execution_guard(self._settings),
                asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
            ):
                runner = Runner(app=app, session_service=session_service, auto_create_session=True)
                async for agent_event in runner.run_async(
                    user_id="event-worker",
                    session_id=f"event-{event.event_id}",
                    invocation_id=event.event_id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part(text=f"Process delivery delay {event.event_id}.")],
                    ),
                ):
                    if isinstance(agent_event.output, dict):
                        output_run_id = agent_event.output.get("run_id")
                        result_ref = agent_event.output.get("result_ref")
                        if isinstance(output_run_id, str) and isinstance(result_ref, str):
                            result = RoutedEventExecution(output_run_id, result_ref)
        except Exception as exc:
            if run_id is not None:
                service.fail_delivery_delay(event.project_id, run_id, exc)
            raise
        if result is None:
            error = RuntimeError("ADK delivery delay workflow completed without a result")
            if run_id is not None:
                service.fail_delivery_delay(event.project_id, run_id, error)
            raise error
        AdkEventExecutor(self._store, self._settings)._persist_adk_identity(
            event.project_id, result.run_id, app_name
        )
        return result

    def _provider(self) -> NotificationProvider:
        if self._notification_provider is not None:
            return self._notification_provider
        if self._settings.notification_provider is NotificationProviderName.LOGGING:
            self._notification_provider = LoggingNotificationProvider()
            return self._notification_provider
        webhook = self._settings.google_chat_webhook_url
        if webhook is None:
            raise RuntimeError("Google Chat delivery notification is not configured")
        self._notification_provider = GoogleChatNotificationProvider(webhook.get_secret_value())
        return self._notification_provider


class AdkEventExecutor:
    """Run one non-site event under an ADK Runner.

    The callback is deliberately limited to the existing typed event service;
    ADK owns invocation/session execution and the service owns domain writes.
    """

    def __init__(self, store: RepositoryStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    async def execute(self, event: ProjectEvent) -> RoutedEventExecution:
        app_name = session_app_name(self._settings, self._store)
        session_id = f"event-{event.event_id}"

        async def execute_typed() -> dict[str, Any]:
            result = TypedEventService(self._store).execute(event)
            return {
                "run_id": result.run_id,
                "result_ref": result.result_ref,
                "waiting_for_approval": result.waiting_for_approval,
            }

        app = App(
            name=app_name,
            root_agent=build_project_event_workflow(
                execute_typed, self._settings.agent_workflow_timeout_seconds
            ),
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        result: RoutedEventExecution | None = None
        async with (
            managed_session_service(self._settings) as session_service,
            sqlite_session_execution_guard(self._settings),
            asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
        ):
            runner = Runner(app=app, session_service=session_service, auto_create_session=True)
            async for agent_event in runner.run_async(
                user_id="event-worker",
                session_id=session_id,
                invocation_id=event.event_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=f"Process project event {event.event_id}.")],
                ),
            ):
                if isinstance(agent_event.output, RequestInput):
                    payload = agent_event.output.payload
                    if isinstance(payload, dict):
                        run_id = payload.get("run_id")
                        result_ref = payload.get("result_ref")
                        if isinstance(run_id, str) and isinstance(result_ref, str):
                            result = RoutedEventExecution(
                                run_id=run_id,
                                result_ref=result_ref,
                                waiting_for_approval=True,
                            )
                elif isinstance(agent_event.output, dict):
                    run_id = agent_event.output.get("run_id")
                    result_ref = agent_event.output.get("result_ref")
                    if isinstance(run_id, str) and isinstance(result_ref, str):
                        result = RoutedEventExecution(
                            run_id=run_id,
                            result_ref=result_ref,
                            waiting_for_approval=bool(
                                agent_event.output.get("waiting_for_approval")
                            ),
                        )
                elif agent_event.content and agent_event.content.parts:
                    for part in agent_event.content.parts:
                        call = part.function_call
                        if call and call.name == "adk_request_input":
                            payload = call.args.get("payload") if call.args else None
                            if isinstance(payload, dict):
                                run_id = payload.get("run_id")
                                result_ref = payload.get("result_ref")
                                if isinstance(run_id, str) and isinstance(result_ref, str):
                                    result = RoutedEventExecution(
                                        run_id=run_id,
                                        result_ref=result_ref,
                                        waiting_for_approval=True,
                                    )
        if result is None:
            raise RuntimeError("ADK event workflow completed without a result")
        self._persist_adk_identity(event.project_id, result.run_id, app_name)
        return result

    def _persist_adk_identity(self, project_id: str, run_id: str, app_name: str) -> None:
        run = self._store.repository(AgentRun).get(project_id, run_id)
        if run is None or run.adk_session_id is None or "/" in run.adk_session_id:
            return
        updated = run.model_copy(
            update={
                "adk_session_id": f"{app_name}/{run.adk_session_id}",
            }
        )
        self._store.repository(AgentRun).save(updated, expected_version=run.version)

    async def resume_approved(self, event: ProjectEvent) -> RoutedEventExecution:
        """Resume the persisted ADK invocation that produced an approval."""
        approval_id = str(event.payload["approval_id"])
        self._store.repository(Approval).require(event.project_id, approval_id)
        requests = [
            item
            for item in self._store.repository(MaterialRequest).list(event.project_id)
            if item.approval_id == approval_id
        ]
        if len(requests) != 1:
            raise RuntimeError("approval must be linked to exactly one material request")
        request = requests[0]
        expected_run_id = run_id_for_event(request.source_event_id)
        runs = [
            item
            for item in self._store.repository(AgentRun).list(event.project_id)
            if item.id == expected_run_id or item.trigger_event_id == request.source_event_id
        ]
        if not runs:
            raise RuntimeError(f"agent run for material request {request.id} was not found")
        run = runs[0]
        if run.workflow is WorkflowName.DAILY_SITE_UPDATE:
            raise RuntimeError(
                "Daily Site Update approvals must resume through SiteUpdateEventExecutor"
            )
        if not run.adk_session_id or not run.adk_invocation_id:
            raise RuntimeError("approval run is missing its persisted ADK invocation")

        async def continue_typed() -> dict[str, str]:
            continuation = ApprovalContinuationService(self._store).handle_approval_granted(
                event.project_id,
                approval_id,
                str(event.payload["resolver"]),
                source_event_id=event.event_id,
                occurred_at=event.occurred_at,
            )
            return {"run_id": continuation.run_id, "result_ref": f"run:{continuation.run_id}"}

        app_name = session_app_name(self._settings, self._store)
        persisted_session = run.adk_session_id
        stored_app_name, separator, session_id = persisted_session.partition("/")
        if not separator:
            stored_app_name = app_name
            session_id = persisted_session
        session_user_id = "event-worker"
        if run.trigger_event_id.startswith("evt_"):
            site_update = self._store.repository(SiteUpdate).get(
                event.project_id,
                f"sup_{run.trigger_event_id.removeprefix('evt_')}",
            )
            if site_update is not None:
                session_user_id = site_update.submitted_by
        app = App(
            name=stored_app_name,
            root_agent=build_project_event_workflow(
                continue_typed, self._settings.agent_workflow_timeout_seconds
            ),
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        result: RoutedEventExecution | None = None
        async with (
            managed_session_service(self._settings) as session_service,
            sqlite_session_execution_guard(self._settings),
            asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
        ):
            session = await session_service.get_session(
                app_name=stored_app_name,
                user_id=session_user_id,
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
            runner = Runner(app=app, session_service=session_service)
            async for agent_event in runner.run_async(
                user_id=session_user_id,
                session_id=session_id,
                invocation_id=run.adk_invocation_id,
                new_message=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call_id,
                                name="adk_request_input",
                                response={"approval": "approved"},
                            )
                        )
                    ],
                ),
            ):
                if isinstance(agent_event.output, dict):
                    run_id = agent_event.output.get("run_id")
                    result_ref = agent_event.output.get("result_ref")
                    if isinstance(run_id, str) and isinstance(result_ref, str):
                        result = RoutedEventExecution(run_id=run_id, result_ref=result_ref)
        if result is None:
            raise RuntimeError("approved ADK workflow completed without a result")
        return result


__all__ = [
    "AdkEventExecutor",
    "build_delivery_delay_workflow",
    "build_project_event_workflow",
]
