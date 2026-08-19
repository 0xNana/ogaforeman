from datetime import UTC, datetime
from typing import Any

import pytest
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from app.agents.adk_runtime import (
    build_site_update_app,
    build_site_update_workflow,
    session_app_name,
)
from app.agents.event_execution import AdkEventExecutor
from app.agents.conversation_execution import AdkConversationExecutor
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.services.routed_events import RoutedEventExecution
from app.services.conversation_action_execution import ConversationActionOutcome


def test_site_update_graph_contains_native_fanout_and_join() -> None:
    async def execute() -> dict[str, str]:
        return {"status": "completed"}

    workflow = build_site_update_workflow(execute, timeout_seconds=10)

    assert workflow.graph is not None
    names = {node.name for node in workflow.graph.nodes}
    assert {
        "progress_node",
        "blocker_node",
        "material_node",
        "merge_branch_results",
        "merge_actions",
        "compose_actions",
        "evaluate_policy",
        "project_daily_log",
        "emit_activity",
    } <= names

    branch_edges = [
        edge for edge in workflow.graph.edges if edge.from_node.name == "interpret_and_route"
    ]
    assert {edge.to_node.name for edge in branch_edges} == {
        "progress_node",
        "blocker_node",
        "material_node",
    }


def test_deployed_adk_namespace_survives_repository_reconstruction() -> None:
    settings = Settings(_env_file=None)
    settings.oga_env = RuntimeEnvironment.STAGING
    settings.google_cloud_project = "oga-project"
    assert session_app_name(settings, object()) == "agents-oga-project"


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
async def test_conversation_action_uses_adk_runner(tmp_path: Any) -> None:
    expected = ConversationActionOutcome(kind="answer", text="done", mutation_performed=False)
    settings = Settings(
        _env_file=None,
        adk_session_backend="database",
        adk_session_database_url=f"sqlite+aiosqlite:///{tmp_path / 'conversation.db'}",
    )

    result = await AdkConversationExecutor(object(), settings).execute(
        session_id="conversation-user_123",
        invocation_id="invocation_123",
        message="What is the project status?",
        action=lambda: _return_outcome(expected),
    )

    assert result == expected


async def _return_outcome(outcome: ConversationActionOutcome) -> ConversationActionOutcome:
    return outcome
