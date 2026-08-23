"""ADK Runner boundary for conversational actions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
import logging
from uuid import uuid4

from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.workflow import Edge, FunctionNode, START, Workflow
from google.adk.agents.context import Context
from google.genai import types

from app.agents.adk_runtime import (
    managed_session_service,
    session_app_name,
    sqlite_session_execution_guard,
)
from app.agents.telemetry import run_adk_stage
from app.agents.identifiers import AdkAgentId, AdkNodeId, AdkToolId, AdkWorkflowId
from app.config.settings import Settings
from app.repositories.interfaces import RepositoryStore


logger = logging.getLogger("ogaforeman.agents.conversation")


ConversationStage = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class AgenticConversationHandlers:
    classify_intent: Callable[[], Awaitable[str]]
    retrieve_authorized_context: ConversationStage
    resolve_entities: ConversationStage
    reason_over_context: ConversationStage
    invoke_typed_tools: ConversationStage


def build_agentic_conversation_workflow(
    handlers: AgenticConversationHandlers,
    timeout: int,
) -> Workflow:
    destination: str | None = None

    async def classify_intent(ctx: Context) -> dict[str, str]:
        nonlocal destination
        destination = await run_adk_stage(
            logger,
            workflow=AdkWorkflowId.PROJECT_CONVERSATION,
            agent=AdkAgentId.PROJECT_CONVERSATION,
            node=AdkNodeId.CLASSIFY_INTENT,
            execute=handlers.classify_intent,
        )
        ctx.route = destination
        return {"destination": destination}

    async def retrieve_authorized_context() -> dict[str, Any]:
        return await run_adk_stage(
            logger,
            workflow=AdkWorkflowId.PROJECT_CONVERSATION,
            agent=AdkAgentId.PROJECT_CONVERSATION,
            node=AdkNodeId.RETRIEVE_AUTHORIZED_CONTEXT,
            execute=handlers.retrieve_authorized_context,
        )

    async def resolve_canonical_entities(ctx: Context) -> dict[str, Any]:
        if destination is None:
            raise RuntimeError("conversation intent stage did not complete")
        result = await run_adk_stage(
            logger,
            workflow=AdkWorkflowId.PROJECT_CONVERSATION,
            agent=AdkAgentId.PROJECT_CONVERSATION,
            node=AdkNodeId.RESOLVE_CANONICAL_ENTITIES,
            execute=handlers.resolve_entities,
        )
        ctx.route = destination
        return result

    async def reason_over_authorized_context() -> dict[str, Any]:
        return await run_adk_stage(
            logger,
            workflow=AdkWorkflowId.PROJECT_CONVERSATION,
            agent=AdkAgentId.PROJECT_CONVERSATION,
            node=AdkNodeId.REASON_OVER_CONTEXT,
            execute=handlers.reason_over_context,
        )

    async def invoke_conversation_typed_tools() -> dict[str, Any]:
        return await run_adk_stage(
            logger,
            workflow=AdkWorkflowId.PROJECT_CONVERSATION,
            agent=AdkAgentId.PROJECT_CONVERSATION,
            node=AdkNodeId.INVOKE_CONVERSATION_TOOLS,
            tool=AdkToolId.CONVERSATION_TOOLS,
            execute=handlers.invoke_typed_tools,
        )

    classify = FunctionNode(func=classify_intent, name=AdkNodeId.CLASSIFY_INTENT, timeout=timeout)
    retrieve = FunctionNode(
        func=retrieve_authorized_context,
        name=AdkNodeId.RETRIEVE_AUTHORIZED_CONTEXT,
        timeout=timeout,
    )
    resolve = FunctionNode(
        func=resolve_canonical_entities,
        name=AdkNodeId.RESOLVE_CANONICAL_ENTITIES,
        timeout=timeout,
    )
    reason = FunctionNode(
        func=reason_over_authorized_context,
        name=AdkNodeId.REASON_OVER_CONTEXT,
        timeout=timeout,
    )
    tools = FunctionNode(
        func=invoke_conversation_typed_tools,
        name=AdkNodeId.INVOKE_CONVERSATION_TOOLS,
        timeout=timeout,
    )
    return Workflow(
        name=AdkWorkflowId.PROJECT_CONVERSATION,
        edges=[
            (START, classify),
            Edge(
                from_node=classify,
                to_node=reason,
                route=[
                    "casual_response",
                    "product_help",
                    "clarification",
                    "confirmation",
                ],
            ),
            Edge(
                from_node=classify,
                to_node=retrieve,
                route=["project_context", "project_advice", "project_action"],
            ),
            Edge(from_node=classify, to_node=tools, route="golden_site_update"),
            (retrieve, resolve),
            Edge(
                from_node=resolve,
                to_node=reason,
                route=["project_context", "project_advice"],
            ),
            Edge(from_node=resolve, to_node=tools, route="project_action"),
        ],
    )


class AdkConversationExecutor:
    """Execute project conversation through the conditional ADK graph."""

    def __init__(self, store: RepositoryStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    async def execute_agentic(
        self,
        *,
        session_id: str,
        invocation_id: str,
        message: str,
        handlers: AgenticConversationHandlers,
    ) -> dict[str, Any]:
        execution_invocation_id = f"{invocation_id}:{uuid4().hex}"
        app = App(
            name=session_app_name(self._settings, self._store),
            root_agent=build_agentic_conversation_workflow(
                handlers, self._settings.agent_workflow_timeout_seconds
            ),
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        result: dict[str, Any] | None = None
        async with (
            managed_session_service(self._settings) as session_service,
            sqlite_session_execution_guard(self._settings),
            asyncio.timeout(self._settings.agent_workflow_timeout_seconds),
        ):
            runner = Runner(app=app, session_service=session_service, auto_create_session=True)
            async for event in runner.run_async(
                user_id=session_id,
                session_id=session_id,
                invocation_id=execution_invocation_id,
                new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            ):
                if (
                    isinstance(event.output, dict)
                    and event.output.get("_conversation_result") is True
                ):
                    result = event.output
        if result is None:
            raise RuntimeError("ADK agentic conversation completed without a result")
        return result


__all__ = [
    "AdkConversationExecutor",
    "AgenticConversationHandlers",
    "build_agentic_conversation_workflow",
]
