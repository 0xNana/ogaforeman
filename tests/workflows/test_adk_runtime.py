from datetime import UTC, datetime
from typing import Any

import pytest
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from app.agents.adk_runtime import (
    SiteUpdateWorkflowHandlers,
    build_site_update_app,
    build_site_update_workflow,
    session_app_name,
)
from app.agents.event_execution import AdkEventExecutor, build_delivery_delay_workflow
from app.agents.conversation_execution import (
    AdkConversationExecutor,
    AgenticConversationHandlers,
    build_agentic_conversation_workflow,
)
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.services.routed_events import RoutedEventExecution, TypedEventService


def test_site_update_graph_contains_native_fanout_and_join() -> None:
    async def execute() -> dict[str, str]:
        return {"status": "completed"}

    workflow = build_site_update_workflow(execute, timeout_seconds=10)

    assert workflow.graph is not None
    names = {node.name for node in workflow.graph.nodes}
    assert {
        "retrieve_authorized_context",
        "interpret_evidence",
        "resolve_canonical_entities",
        "progress_node",
        "blocker_node",
        "material_node",
        "merge_branch_results",
        "merge_actions",
        "evaluate_policy",
        "execute_site_update",
        "project_daily_log",
        "emit_activity",
    } <= names

    branch_edges = [
        edge for edge in workflow.graph.edges if edge.from_node.name == "resolve_canonical_entities"
    ]
    assert {edge.to_node.name for edge in branch_edges} == {
        "progress_node",
        "blocker_node",
        "material_node",
    }


@pytest.mark.asyncio
async def test_site_update_graph_invokes_real_stage_handlers(tmp_path: Any) -> None:
    calls: list[str] = []

    def stage(name: str, result: dict[str, object] | None = None):
        async def execute() -> dict[str, object]:
            calls.append(name)
            return result or {"stage": name}

        return execute

    handlers = SiteUpdateWorkflowHandlers(
        receive_input=stage("receive"),
        prepare_evidence=stage("prepare"),
        retrieve_context=stage("context"),
        interpret_evidence=stage("interpret"),
        resolve_entities=stage("resolve"),
        analyze_progress=stage("progress"),
        analyze_blockers=stage("blockers"),
        analyze_materials=stage("materials"),
        merge_results=stage("merge"),
        apply_policy=stage("policy"),
        invoke_typed_tools=stage(
            "tools",
            {
                "status": "completed",
                "has_pending_approvals": False,
                "has_clarifications": False,
                "has_safety_stops": False,
            },
        ),
        project_daily_log=stage("report"),
        emit_activity=stage("activity"),
        complete=stage("complete"),
    )
    runner = Runner(
        app=build_site_update_app(
            "site-update-stage-test",
            handlers=handlers,
            timeout_seconds=10,
        ),
        session_service=DatabaseSessionService(
            f"sqlite+aiosqlite:///{tmp_path / 'site-update-stages.db'}"
        ),
        auto_create_session=True,
    )

    _ = [
        event
        async for event in runner.run_async(
            user_id="usr_manager123",
            session_id="run_stage_test",
            invocation_id="evt_stage_test",
            new_message=types.Content(role="user", parts=[types.Part(text="Run stages")]),
        )
    ]

    assert calls[:5] == ["receive", "prepare", "context", "interpret", "resolve"]
    assert set(calls[5:8]) == {"progress", "blockers", "materials"}
    assert calls[8:] == ["merge", "policy", "tools", "report", "activity", "complete"]


def test_deployed_adk_namespace_survives_repository_reconstruction() -> None:
    settings = Settings(_env_file=None)
    settings.oga_env = RuntimeEnvironment.STAGING
    settings.google_cloud_project = "oga-project"
    assert session_app_name(settings, object()) == "agents-oga-project"


def test_delivery_delay_graph_exposes_context_impact_and_each_typed_tool() -> None:
    async def stage() -> dict[str, str]:
        return {"status": "ok"}

    names = (
        "receive_delivery_delay",
        "retrieve_authorized_request_context",
        "assess_material_schedule_impact",
        "mark_material_request_delayed_tool",
        "create_delivery_risk_tool",
        "create_delivery_follow_up_tool",
        "deliver_delivery_notification_tool",
        "complete_delivery_delay",
    )
    workflow = build_delivery_delay_workflow({name: stage for name in names}, 10)

    assert workflow.name == "delivery_delay_workflow"
    assert workflow.graph is not None
    assert set(names) <= {node.name for node in workflow.graph.nodes}


def test_legacy_route_map_cannot_execute_delivery_delay() -> None:
    event = ProjectEvent(
        event_id="evt_delivery_delay_route_guard",
        project_id="prj_route_guard",
        event_type=EventType.DELIVERY_DELAYED,
        source=EventSource.WEB,
        actor=EventActor(
            type=EventActorType.USER,
            id="usr_manager_route_guard",
        ),
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        idempotency_key="delivery-delay-route-guard",
        correlation_id="cor_delivery_delay_route_guard",
        payload={
            "request_id": "mrq_route_guard",
            "new_date": "2026-08-24",
            "reason": "Supplier rescheduled delivery.",
        },
    )

    with pytest.raises(
        ValueError,
        match="routed event executor does not support DELIVERY_DELAYED",
    ):
        TypedEventService(object()).execute(event)  # type: ignore[arg-type]


def test_agentic_conversation_graph_owns_reasoning_and_tool_routes() -> None:
    async def classify() -> str:
        return "project_context"

    async def stage() -> dict[str, object]:
        return {}

    workflow = build_agentic_conversation_workflow(
        AgenticConversationHandlers(
            classify_intent=classify,
            retrieve_authorized_context=stage,
            resolve_entities=stage,
            reason_over_context=stage,
            invoke_typed_tools=stage,
        ),
        10,
    )

    assert workflow.name == "agentic_project_conversation"
    assert workflow.graph is not None
    assert {
        "classify_intent",
        "retrieve_authorized_context",
        "resolve_canonical_entities",
        "reason_over_authorized_context",
        "invoke_conversation_typed_tools",
    } <= {node.name for node in workflow.graph.nodes}


@pytest.mark.asyncio
async def test_runner_resumes_the_original_invocation_after_session_service_reconstruction(
    tmp_path: Any,
) -> None:
    """An approval pause must resume ADK work rather than restart custom state."""

    calls = 0

    async def execute() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "summary": "Approval is required.",
                "has_pending_approvals": True,
                "has_clarifications": False,
                "has_safety_stops": False,
            }
        return {
            "status": "completed",
            "has_pending_approvals": False,
            "has_clarifications": False,
            "has_safety_stops": False,
        }

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'adk-sessions.db'}"
    app_name = "oga-adk-resume-test"
    session_id = "run_123-attempt-1"
    invocation_id = "evt_123"

    first_runner = Runner(
        app=build_site_update_app(app_name, execute, timeout_seconds=10),
        session_service=DatabaseSessionService(database_url),
        auto_create_session=True,
    )
    first_events = [
        event
        async for event in first_runner.run_async(
            user_id="usr_manager123",
            session_id=session_id,
            invocation_id=invocation_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Process the persisted update.")]
            ),
        )
    ]
    assert calls == 1
    assert any(
        part.function_call and part.function_call.name == "adk_request_input"
        for event in first_events
        for part in (event.content.parts if event.content else [])
    )
    approval_call = next(
        part.function_call
        for event in first_events
        for part in (event.content.parts if event.content else [])
        if part.function_call and part.function_call.name == "adk_request_input"
    )
    assert approval_call is not None

    restarted_runner = Runner(
        app=build_site_update_app(app_name, execute, timeout_seconds=10),
        session_service=DatabaseSessionService(database_url),
    )
    resumed_events = [
        event
        async for event in restarted_runner.run_async(
            user_id="usr_manager123",
            session_id=session_id,
            invocation_id=invocation_id,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=approval_call.id,
                            name=approval_call.name,
                            response={"approval": "approved"},
                        )
                    )
                ],
            ),
        )
    ]

    assert calls == 2
    assert not any(
        part.function_call and part.function_call.name == "adk_request_input"
        for event in resumed_events
        for part in (event.content.parts if event.content else [])
    )


@pytest.mark.asyncio
async def test_non_site_event_uses_adk_runner_before_typed_event_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    expected = RoutedEventExecution(run_id="run_task", result_ref="task:task_1")

    def execute(self: Any, event: ProjectEvent) -> RoutedEventExecution:
        assert event.event_type is EventType.TASK_COMPLETED
        return expected

    monkeypatch.setattr("app.agents.event_execution.TypedEventService.execute", execute)
    now = datetime.now(UTC)
    event = ProjectEvent(
        event_id="evt_task_123",
        project_id="project_123",
        event_type=EventType.TASK_COMPLETED,
        source=EventSource.SYSTEM,
        occurred_at=now,
        received_at=now,
        actor=EventActor(type=EventActorType.SYSTEM, id="system_agent"),
        idempotency_key="idem_task_123",
        correlation_id="corr_task_123",
        payload={"task_id": "task_123", "evidence_refs": ["photo_1"]},
    )
    settings = Settings(
        _env_file=None,
        adk_session_backend="database",
        adk_session_database_url=f"sqlite+aiosqlite:///{tmp_path / 'event.db'}",
    )

    result = await AdkEventExecutor(object(), settings).execute(event)

    assert result == expected


@pytest.mark.asyncio
async def test_agentic_conversation_uses_adk_runner_and_typed_tool_route(tmp_path: Any) -> None:
    settings = Settings(
        _env_file=None,
        adk_session_backend="database",
        adk_session_database_url=f"sqlite+aiosqlite:///{tmp_path / 'conversation.db'}",
    )

    calls: list[str] = []

    async def classify() -> str:
        calls.append("classify")
        return "project_action"

    async def context() -> dict[str, object]:
        calls.append("context")
        return {}

    async def resolve() -> dict[str, object]:
        calls.append("resolve")
        return {}

    async def unused_reason() -> dict[str, object]:
        raise AssertionError("project action must not use the answer branch")

    async def tools() -> dict[str, object]:
        calls.append("tools")
        return {"_conversation_result": True, "kind": "done", "text": "done"}

    result = await AdkConversationExecutor(object(), settings).execute_agentic(
        session_id="conversation-user_123",
        invocation_id="invocation_123",
        message="What is the project status?",
        handlers=AgenticConversationHandlers(
            classify_intent=classify,
            retrieve_authorized_context=context,
            resolve_entities=resolve,
            reason_over_context=unused_reason,
            invoke_typed_tools=tools,
        ),
    )

    assert result["kind"] == "done"
    assert calls == ["classify", "context", "resolve", "tools"]
