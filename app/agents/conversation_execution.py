"""ADK Runner boundary for conversational actions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.workflow import FunctionNode, START, Workflow
from google.genai import types

from app.agents.adk_runtime import (
    managed_session_service,
    session_app_name,
    sqlite_session_execution_guard,
)
from app.config.settings import Settings
from app.repositories.interfaces import RepositoryStore
from app.services.conversation_action_execution import ConversationActionOutcome


def _workflow(
    execute: Callable[[], Awaitable[ConversationActionOutcome]], timeout: int
) -> Workflow:
    async def run_action() -> ConversationActionOutcome:
        return await execute()

    return Workflow(
        name="conversation_action_workflow",
        edges=[(START, FunctionNode(func=run_action, name="execute_action", timeout=timeout))],
    )


class AdkConversationExecutor:
    """Execute a conversation action through ADK while retaining typed services."""

    def __init__(self, store: RepositoryStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    async def execute(
        self,
        *,
        session_id: str,
        invocation_id: str,
        message: str,
        action: Callable[[], Awaitable[ConversationActionOutcome]],
    ) -> ConversationActionOutcome:
        # The domain idempotency key remains the mutation claim.  ADK
        # invocation IDs are execution cursors, so each HTTP delivery gets a
        # fresh cursor; this lets a replay reach the typed service, which can
        # return its durable no-op outcome without asking ADK to rerun a
        # completed invocation.
        execution_invocation_id = f"{invocation_id}:{uuid4().hex}"
        app = App(
            name=session_app_name(self._settings, self._store),
            root_agent=_workflow(action, self._settings.agent_workflow_timeout_seconds),
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        result: ConversationActionOutcome | None = None
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
                if isinstance(event.output, ConversationActionOutcome):
                    result = event.output
        if result is None:
            raise RuntimeError("ADK conversation workflow completed without a result")
        return result


__all__ = ["AdkConversationExecutor"]
