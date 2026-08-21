"""ADK entrypoint for persisted non-site agentic events."""

from __future__ import annotations

import asyncio
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
from app.config.settings import Settings
from app.domain.events import ProjectEvent
from app.repositories.interfaces import RepositoryStore
from app.services.routed_events import RoutedEventExecution, TypedEventService
from app.domain.models import Approval, MaterialRequest, AgentRun, SiteUpdate
from app.workflows.resume import ApprovalContinuationService
from app.repositories.runs import run_id_for_event


def _build_event_workflow(execute: Any, timeout_seconds: int) -> Workflow:
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
    return Workflow(name="project_event_workflow", edges=[(START, node)])


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
            root_agent=_build_event_workflow(
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
        return result

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
            root_agent=_build_event_workflow(
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


__all__ = ["AdkEventExecutor"]
