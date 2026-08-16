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
from google.adk.workflow import FunctionNode, JoinNode, START, Workflow
from google.adk.agents.context import Context
from pydantic import BaseModel, Field

from app.config.settings import RuntimeEnvironment, Settings


class SiteUpdateWorkflowState(BaseModel):
    """Serializable state owned by the native ADK site-update graph."""

    stage: str = "created"
    stage_history: list[str] = Field(default_factory=list)
    branches_completed: list[str] = Field(default_factory=list)
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

    async def receive_input(ctx: Context) -> dict[str, str]:
        ctx.state["stage"] = "received"
        ctx.state["stage_history"] = ["receive_input"]
        return {"stage": "received"}

    async def prepare_multimodal_input(ctx: Context) -> dict[str, str]:
        ctx.state["stage"] = "prepared"
        history = list(ctx.state.get("stage_history", []))
        history.append("prepare_multimodal_input")
        ctx.state["stage_history"] = history
        return {"stage": "prepared"}

    async def interpret_and_route(ctx: Context) -> dict[str, str]:
        ctx.state["stage"] = "interpreting"
        history = list(ctx.state.get("stage_history", []))
        history.append("interpret_and_route")
        ctx.state["stage_history"] = history
        return {"stage": "interpreting"}

    async def execute_site_update(ctx: Context) -> Any:
        result = await execute()
        if isinstance(result, dict):
            ctx.state["stage"] = "tools_executed"
            ctx.state["result"] = result
            history = list(ctx.state.get("stage_history", []))
            history.append("execute_tools")
            ctx.state["stage_history"] = history
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

    async def progress_node(ctx: Context) -> dict[str, str]:
        branches = list(ctx.state.get("branches_completed", []))
        branches.append("progress")
        ctx.state["branches_completed"] = branches
        return {"branch": "progress"}

    async def blocker_node(ctx: Context) -> dict[str, str]:
        branches = list(ctx.state.get("branches_completed", []))
        branches.append("blocker")
        ctx.state["branches_completed"] = branches
        return {"branch": "blocker"}

    async def material_node(ctx: Context) -> dict[str, str]:
        branches = list(ctx.state.get("branches_completed", []))
        branches.append("material")
        ctx.state["branches_completed"] = branches
        return {"branch": "material"}

    async def merge_actions(ctx: Context) -> dict[str, str]:
        history = list(ctx.state.get("stage_history", []))
        history.append("merge_actions")
        ctx.state["stage_history"] = history
        return {"stage": "merged"}

    async def compose_actions(ctx: Context) -> dict[str, str]:
        history = list(ctx.state.get("stage_history", []))
        history.append("compose_actions")
        ctx.state["stage_history"] = history
        return {"stage": "composed"}

    async def evaluate_policy(ctx: Context) -> dict[str, str]:
        history = list(ctx.state.get("stage_history", []))
        history.append("evaluate_policy")
        ctx.state["stage_history"] = history
        return {"stage": "policy_evaluated"}

    async def finalize_site_update(ctx: Context) -> dict[str, Any]:
        ctx.state["stage"] = "completed"
        history = list(ctx.state.get("stage_history", []))
        history.append("completion")
        ctx.state["stage_history"] = history
        return ctx.state.get("result") or {}

    async def project_daily_log(ctx: Context) -> dict[str, str]:
        history = list(ctx.state.get("stage_history", []))
        history.append("project_daily_log")
        ctx.state["stage_history"] = history
        return {"stage": "daily_log_projected"}

    async def emit_activity(ctx: Context) -> dict[str, str]:
        history = list(ctx.state.get("stage_history", []))
        history.append("emit_activity")
        ctx.state["stage_history"] = history
        return {"stage": "activity_emitted"}

    receive = FunctionNode(func=receive_input, name="receive_input", timeout=timeout_seconds)
    prepare = FunctionNode(
        func=prepare_multimodal_input,
        name="prepare_multimodal_input",
        timeout=timeout_seconds,
    )
    interpret = FunctionNode(
        func=interpret_and_route,
        name="interpret_and_route",
        timeout=timeout_seconds,
    )
    progress = FunctionNode(func=progress_node, name="progress_node", timeout=timeout_seconds)
    blocker = FunctionNode(func=blocker_node, name="blocker_node", timeout=timeout_seconds)
    material = FunctionNode(func=material_node, name="material_node", timeout=timeout_seconds)
    branch_join = JoinNode(name="merge_branch_results")
    merge = FunctionNode(func=merge_actions, name="merge_actions", timeout=timeout_seconds)
    compose = FunctionNode(func=compose_actions, name="compose_actions", timeout=timeout_seconds)
    policy = FunctionNode(func=evaluate_policy, name="evaluate_policy", timeout=timeout_seconds)
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
    daily_log = FunctionNode(
        func=project_daily_log,
        name="project_daily_log",
        timeout=timeout_seconds,
    )
    activity = FunctionNode(func=emit_activity, name="emit_activity", timeout=timeout_seconds)
    return Workflow(
        name="daily_site_update_workflow",
        state_schema=SiteUpdateWorkflowState,
        edges=[
            (START, receive, prepare, interpret),
            (interpret, (progress, blocker, material)),
            (progress, branch_join),
            (blocker, branch_join),
            (material, branch_join),
            (branch_join, merge, compose, policy, execute_node),
            (execute_node, daily_log, activity, finalize),
        ],
    )


__all__ = ["build_site_update_workflow", "create_session_service"]
