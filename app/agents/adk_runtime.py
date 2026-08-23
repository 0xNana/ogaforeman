"""ADK runtime construction and native workflow graph for site updates.

The application owns domain mutations; ADK owns graph execution and session
history.  Keeping construction here makes accidental in-memory production
sessions difficult and gives tests one explicit seam for a local durable DB.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
import inspect
from pathlib import Path
from threading import Lock
from typing import Any

from google.adk.sessions import BaseSessionService
from google.adk.apps import App, ResumabilityConfig
from google.adk.events import RequestInput
from google.adk.workflow import FunctionNode, JoinNode, START, Workflow
from google.adk.agents.context import Context
from pydantic import BaseModel, Field

from app.config.settings import RuntimeEnvironment, Settings
from app.agents.identifiers import AdkNodeId, AdkWorkflowId


_SQLITE_SESSION_LOCKS: dict[str, Lock] = {}
_SQLITE_SESSION_LOCKS_GUARD = Lock()


class SiteUpdateWorkflowState(BaseModel):
    """Serializable state owned by the native ADK site-update graph."""

    stage: str = "created"
    stage_history: list[str] = Field(default_factory=list)
    branches_completed: list[str] = Field(default_factory=list)
    branch_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    progress_ready: bool = False
    blocker_ready: bool = False
    material_ready: bool = False
    result: dict[str, Any] | None = None


SiteUpdateStage = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class SiteUpdateWorkflowHandlers:
    """Application-owned stage implementations scheduled by ADK.

    A handler may call Gemini, an authorized repository reader, or a typed
    mutation tool. The graph, rather than a handler, owns stage ordering,
    branch fan-out/fan-in, interruption, and continuation.
    """

    receive_input: SiteUpdateStage
    prepare_evidence: SiteUpdateStage
    retrieve_context: SiteUpdateStage
    interpret_evidence: SiteUpdateStage
    resolve_entities: SiteUpdateStage
    analyze_progress: SiteUpdateStage
    analyze_blockers: SiteUpdateStage
    analyze_materials: SiteUpdateStage
    merge_results: SiteUpdateStage
    apply_policy: SiteUpdateStage
    invoke_typed_tools: SiteUpdateStage
    project_daily_log: SiteUpdateStage
    emit_activity: SiteUpdateStage
    complete: SiteUpdateStage


async def _empty_stage() -> dict[str, Any]:
    return {}


def _legacy_site_update_handlers(execute: SiteUpdateStage) -> SiteUpdateWorkflowHandlers:
    """Keep the public builder compatible while callers migrate to handlers."""

    return SiteUpdateWorkflowHandlers(
        receive_input=_empty_stage,
        prepare_evidence=_empty_stage,
        retrieve_context=_empty_stage,
        interpret_evidence=_empty_stage,
        resolve_entities=_empty_stage,
        analyze_progress=_empty_stage,
        analyze_blockers=_empty_stage,
        analyze_materials=_empty_stage,
        merge_results=_empty_stage,
        apply_policy=_empty_stage,
        invoke_typed_tools=execute,
        project_daily_log=_empty_stage,
        emit_activity=_empty_stage,
        complete=_empty_stage,
    )


def create_session_service(settings: Settings) -> BaseSessionService:
    """Build the configured ADK session backend.

    Deployed environments are required to use Agent Platform Sessions.  A
    SQLite-backed ADK service is intentionally limited to local/test use.
    """

    backend = settings.adk_session_backend
    if backend == "auto":
        backend = (
            "vertex_ai"
            if settings.oga_env
            in {
                RuntimeEnvironment.PREVIEW,
                RuntimeEnvironment.STAGING,
                RuntimeEnvironment.PRODUCTION,
            }
            else "database"
        )

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
            # SQLite permits one writer.  The finite connection timeout also
            # protects local multi-process development, while the execution
            # guard below handles concurrent deliveries in this process.
            return DatabaseSessionService(
                settings.adk_session_database_url,
                connect_args={"timeout": 30},
            )
        return DatabaseSessionService(settings.adk_session_database_url)

    raise ValueError(
        "Unsupported ADK_SESSION_BACKEND; use 'database' locally or 'vertex_ai' in deployment"
    )


@asynccontextmanager
async def managed_session_service(settings: Settings) -> AsyncIterator[BaseSessionService]:
    """Yield a session service and always release its database resources."""

    service = create_session_service(settings)
    try:
        yield service
    finally:
        close = getattr(service, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


@asynccontextmanager
async def sqlite_session_execution_guard(settings: Settings) -> AsyncIterator[None]:
    """Serialize local SQLite ADK writes without limiting deployed backends.

    ADK stores shared app and user state whenever it creates or appends a
    session. Independent ``DatabaseSessionService`` instances otherwise race
    on SQLite's single-writer lock under concurrent event delivery. Waiting
    for a thread lock through ``to_thread`` keeps a shared event loop live.
    """

    database_url = settings.adk_session_database_url
    if not database_url.startswith("sqlite"):
        yield
        return
    with _SQLITE_SESSION_LOCKS_GUARD:
        lock = _SQLITE_SESSION_LOCKS.setdefault(database_url, Lock())
    await asyncio.to_thread(lock.acquire)
    try:
        yield
    finally:
        lock.release()


def session_app_name(settings: Settings, store: object) -> str:
    """Return a stable ADK app namespace for session lookup.

    Production restarts reconstruct repository objects, so their Python
    identity must never be part of an ADK session key. Local tests use store
    identity only to prevent one test's SQLite session history contaminating
    another test.
    """

    if settings.oga_env in {
        RuntimeEnvironment.PREVIEW,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
    }:
        project = settings.google_cloud_project or "oga"
        return f"agents-{project}"
    return f"agents-local-{id(store)}"


def build_site_update_workflow(
    execute: SiteUpdateStage | None = None,
    *,
    timeout_seconds: int,
    handlers: SiteUpdateWorkflowHandlers | None = None,
) -> Workflow:
    """Create the native ADK graph used by the Daily Site Update worker.

    The execution callback is an application boundary containing typed tools;
    ADK still owns node scheduling, event history, retries, and resumption.
    The explicit graph leaves room for adding domain-specialized nodes without
    reintroducing a second orchestration loop.
    """

    if handlers is None:
        if execute is None:
            raise ValueError("site update workflow requires stage handlers")
        handlers = _legacy_site_update_handlers(execute)

    async def _run_stage(
        ctx: Context,
        stage: str,
        handler: SiteUpdateStage,
    ) -> dict[str, Any]:
        result = await handler()
        history = list(ctx.state.get("stage_history", []))
        history.append(stage)
        ctx.state["stage_history"] = history
        ctx.state["stage"] = stage
        return result

    async def receive_input(ctx: Context) -> dict[str, Any]:
        ctx.state["stage"] = "received"
        ctx.state["stage_history"] = []
        return await _run_stage(ctx, "receive_input", handlers.receive_input)

    async def prepare_multimodal_input(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "prepare_evidence", handlers.prepare_evidence)

    async def retrieve_authorized_context(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "retrieve_context", handlers.retrieve_context)

    async def interpret_evidence(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "interpret_evidence", handlers.interpret_evidence)

    async def resolve_canonical_entities(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "resolve_entities", handlers.resolve_entities)

    async def execute_site_update(ctx: Context) -> Any:
        result = await handlers.invoke_typed_tools()
        if isinstance(result, dict):
            ctx.state["stage"] = "tools_executed"
            ctx.state["result"] = result
            history = list(ctx.state.get("stage_history", []))
            history.append("execute_tools")
            ctx.state["stage_history"] = history
        if result.get("has_clarifications") or result.get("has_safety_stops"):
            return RequestInput(
                interrupt_id=(
                    "clarification_needed" if result.get("has_clarifications") else "safety_stop"
                ),
                message=result.get("summary", ""),
                payload=result,
                response_schema=dict[str, Any],
            )
        if result.get("has_pending_approvals"):
            return RequestInput(
                interrupt_id="approval_required",
                message=result.get("summary", ""),
                payload=result,
                response_schema=dict[str, Any],
            )
        return result

    def _complete_branch(ctx: Context, branch: str, result: dict[str, Any]) -> dict[str, Any]:
        ctx.state[f"{branch}_ready"] = True
        branch_results = dict(ctx.state.get("branch_results", {}))
        branch_results[branch] = result
        ctx.state["branch_results"] = branch_results
        return result

    async def progress_node(ctx: Context) -> dict[str, Any]:
        result = await _run_stage(ctx, "analyze_progress", handlers.analyze_progress)
        return _complete_branch(ctx, "progress", result)

    async def blocker_node(ctx: Context) -> dict[str, Any]:
        result = await _run_stage(ctx, "analyze_blockers", handlers.analyze_blockers)
        return _complete_branch(ctx, "blocker", result)

    async def material_node(ctx: Context) -> dict[str, Any]:
        result = await _run_stage(ctx, "analyze_materials", handlers.analyze_materials)
        return _complete_branch(ctx, "material", result)

    async def merge_actions(ctx: Context) -> dict[str, str]:
        expected = {"progress", "blocker", "material"}
        completed = {branch for branch in expected if ctx.state.get(f"{branch}_ready", False)}
        missing = expected - completed
        if missing:
            raise RuntimeError(f"ADK fan-in missing branches: {sorted(missing)}")
        ctx.state["branches_completed"] = sorted(completed)
        return await _run_stage(ctx, "merge_results", handlers.merge_results)

    async def evaluate_policy(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "apply_policy", handlers.apply_policy)

    async def finalize_site_update(ctx: Context) -> dict[str, Any]:
        await _run_stage(ctx, "complete", handlers.complete)
        ctx.state["stage"] = "completed"
        return ctx.state.get("result") or {}

    async def project_daily_log(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "project_daily_log", handlers.project_daily_log)

    async def emit_activity(ctx: Context) -> dict[str, Any]:
        return await _run_stage(ctx, "emit_activity", handlers.emit_activity)

    receive = FunctionNode(
        func=receive_input, name=AdkNodeId.RECEIVE_INPUT, timeout=timeout_seconds
    )
    prepare = FunctionNode(
        func=prepare_multimodal_input,
        name=AdkNodeId.PREPARE_MULTIMODAL_INPUT,
        timeout=timeout_seconds,
    )
    retrieve = FunctionNode(
        func=retrieve_authorized_context,
        name=AdkNodeId.RETRIEVE_AUTHORIZED_CONTEXT,
        timeout=timeout_seconds,
    )
    interpret = FunctionNode(
        func=interpret_evidence,
        name=AdkNodeId.INTERPRET_EVIDENCE,
        timeout=timeout_seconds,
    )
    resolve = FunctionNode(
        func=resolve_canonical_entities,
        name=AdkNodeId.RESOLVE_CANONICAL_ENTITIES,
        timeout=timeout_seconds,
    )
    progress = FunctionNode(
        func=progress_node, name=AdkNodeId.PROGRESS, timeout=timeout_seconds
    )
    blocker = FunctionNode(
        func=blocker_node, name=AdkNodeId.BLOCKER, timeout=timeout_seconds
    )
    material = FunctionNode(
        func=material_node, name=AdkNodeId.MATERIAL, timeout=timeout_seconds
    )
    branch_join = JoinNode(name=AdkNodeId.MERGE_BRANCH_RESULTS)
    merge = FunctionNode(
        func=merge_actions, name=AdkNodeId.MERGE_ACTIONS, timeout=timeout_seconds
    )
    policy = FunctionNode(
        func=evaluate_policy, name=AdkNodeId.EVALUATE_POLICY, timeout=timeout_seconds
    )
    execute_node = FunctionNode(
        func=execute_site_update,
        name=AdkNodeId.EXECUTE_SITE_UPDATE,
        rerun_on_resume=True,
        timeout=timeout_seconds,
    )
    finalize = FunctionNode(
        func=finalize_site_update,
        name=AdkNodeId.FINALIZE_SITE_UPDATE,
        timeout=timeout_seconds,
    )
    daily_log = FunctionNode(
        func=project_daily_log,
        name=AdkNodeId.PROJECT_DAILY_LOG,
        timeout=timeout_seconds,
    )
    activity = FunctionNode(
        func=emit_activity, name=AdkNodeId.EMIT_ACTIVITY, timeout=timeout_seconds
    )
    return Workflow(
        name=AdkWorkflowId.DAILY_SITE_UPDATE,
        state_schema=SiteUpdateWorkflowState,
        edges=[
            (START, receive, prepare, retrieve, interpret, resolve),
            (resolve, (progress, blocker, material)),
            (progress, branch_join),
            (blocker, branch_join),
            (material, branch_join),
            (branch_join, merge, policy, execute_node),
            (execute_node, daily_log, activity, finalize),
        ],
    )


def build_site_update_app(
    app_name: str,
    execute: SiteUpdateStage | None = None,
    *,
    timeout_seconds: int,
    handlers: SiteUpdateWorkflowHandlers | None = None,
) -> App:
    """Build the resumable ADK application for one site-update invocation."""

    return App(
        name=app_name,
        root_agent=build_site_update_workflow(
            execute,
            handlers=handlers,
            timeout_seconds=timeout_seconds,
        ),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


__all__ = [
    "build_site_update_app",
    "build_site_update_workflow",
    "SiteUpdateWorkflowHandlers",
    "create_session_service",
    "managed_session_service",
    "session_app_name",
    "sqlite_session_execution_guard",
]
