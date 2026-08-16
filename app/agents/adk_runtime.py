"""ADK runtime construction and native workflow graph for site updates.

The application owns domain mutations; ADK owns graph execution and session
history.  Keeping construction here makes accidental in-memory production
sessions difficult and gives tests one explicit seam for a local durable DB.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from google.adk.sessions import BaseSessionService
from google.adk.events import RequestInput
from google.adk.workflow import FunctionNode, START, Workflow
from google.adk.agents.context import Context
from pydantic import BaseModel

from app.config.settings import RuntimeEnvironment, Settings


class SiteUpdateWorkflowState(BaseModel):
    """Serializable state owned by the native ADK site-update graph."""

    stage: str = "created"
    result: dict[str, Any] | None = None


def create_session_service(settings: Settings) -> BaseSessionService:
    """Build the configured ADK session backend.

    Deployed environments are required to use Agent Platform Sessions.  A
    SQLite-backed ADK service is intentionally limited to local/test use.
    """

    backend = settings.adk_session_backend
    if backend == "auto":
        backend = "vertex_ai" if settings.oga_env in {
            RuntimeEnvironment.PREVIEW,
            RuntimeEnvironment.STAGING,
            RuntimeEnvironment.PRODUCTION,
        } else "database"

    if backend == "vertex_ai":
        if not settings.google_cloud_project or not settings.google_cloud_region:
            raise ValueError("Vertex AI ADK sessions require project and region")
        if not settings.adk_agent_engine_id:
            raise ValueError("Vertex AI ADK sessions require ADK_AGENT_ENGINE_ID")
        from google.adk.sessions import VertexAiSessionService

        return VertexAiSessionService(
            project=settings.google_cloud_project,
            location=settings.google_cloud_region,
            agent_engine_id=settings.adk_agent_engine_id,
        )

    if backend == "database":
        from google.adk.sessions import DatabaseSessionService

        if settings.adk_session_database_url.startswith("sqlite"):
            Path(".adk").mkdir(parents=True, exist_ok=True)
        return DatabaseSessionService(settings.adk_session_database_url)

    raise ValueError(
        "Unsupported ADK_SESSION_BACKEND; use 'database' locally or 'vertex_ai' in deployment"
    )


def build_site_update_workflow(
    execute: Callable[[], Awaitable[dict[str, Any]]],
    *,
    timeout_seconds: int,
) -> Workflow:
    """Create the native ADK graph used by the Daily Site Update worker.

    The execution callback is an application boundary containing typed tools;
    ADK still owns node scheduling, event history, retries, and resumption.
    The explicit graph leaves room for adding domain-specialized nodes without
    reintroducing a second orchestration loop.
    """

    async def load_site_update(ctx: Context) -> dict[str, str]:
        ctx.state["stage"] = "loaded"
        return {"stage": "loaded"}

    async def execute_site_update(ctx: Context) -> Any:
        result = await execute()
        if isinstance(result, dict):
            ctx.state["stage"] = "executed"
            ctx.state["result"] = result
        if result.get("has_clarifications") or result.get("has_safety_stops"):
            return RequestInput(
                interrupt_id=(
                    "clarification_needed"
                    if result.get("has_clarifications")
                    else "safety_stop"
                ),
                message=result.get("summary", ""),
                payload=result,
            )
        if result.get("has_pending_approvals"):
            return RequestInput(
                interrupt_id="approval_required",
                message=result.get("summary", ""),
                payload=result,
            )
        return result

    async def finalize_site_update(ctx: Context) -> dict[str, Any]:
        ctx.state["stage"] = "finalized"
        return ctx.state.get("result") or {}

    load = FunctionNode(func=load_site_update, name="load_site_update", timeout=timeout_seconds)
    execute_node = FunctionNode(
        func=execute_site_update,
        name="execute_site_update",
        rerun_on_resume=True,
        timeout=timeout_seconds,
    )
    finalize = FunctionNode(
        func=finalize_site_update,
        name="finalize_site_update",
        timeout=timeout_seconds,
    )
    return Workflow(
        name="daily_site_update_workflow",
        state_schema=SiteUpdateWorkflowState,
        edges=[
            (START, load, execute_node),
            (execute_node, finalize),
        ],
    )


__all__ = ["build_site_update_workflow", "create_session_service"]
