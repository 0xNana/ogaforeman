"""Exercise native ADK pause/resume against the configured Vertex session backend."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import inspect
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.adk.sessions import VertexAiSessionService
from google.genai import types
from pydantic import BaseModel, ConfigDict

from app.agents.adk_runtime import build_site_update_app, create_session_service
from app.agents.identifiers import AdkWorkflowId
from app.config.settings import RuntimeEnvironment, Settings


# Vertex Agent Engine Sessions rejects TTL values shorter than 24 hours.
RUNTIME_SESSION_TTL = "86400s"


class RuntimeCheckConfig(BaseModel):
    """Non-secret Vertex configuration used by the runtime smoke."""

    model_config = ConfigDict(frozen=True)

    project: str
    location: str
    engine_id: str
    app_name: str


class RuntimeCheckState(BaseModel):
    """Identifiers shared between isolated pause, resume, and cleanup processes."""

    project: str
    location: str
    engine_id: str
    app_name: str
    user_id: str
    session_id: str
    invocation_id: str
    approval_call_id: str | None = None
    approval_call_name: str | None = None
    created_at: datetime


SessionServiceFactory = Callable[[RuntimeCheckConfig], BaseSessionService]


def load_runtime_config(env_file: Path) -> RuntimeCheckConfig:
    """Load production field names while ignoring unrelated deployment requirements."""

    settings = Settings(  # type: ignore[call-arg]
        _env_file=env_file,
        oga_env=RuntimeEnvironment.LOCAL,
        adk_session_backend="vertex_ai",
    )
    project = settings.google_cloud_project
    location = settings.google_cloud_region
    engine_id = settings.adk_agent_engine_id
    if not project:
        raise ValueError("Set GOOGLE_CLOUD_PROJECT")
    if not location:
        raise ValueError("Set GOOGLE_CLOUD_REGION")
    if not engine_id:
        raise ValueError("Set ADK_AGENT_ENGINE_ID")
    if not engine_id.isdigit():
        raise ValueError("ADK_AGENT_ENGINE_ID must be a numeric Reasoning Engine ID")
    return RuntimeCheckConfig(
        project=project,
        location=location,
        engine_id=engine_id,
        app_name=f"agents-{project}",
    )


def vertex_session_service(config: RuntimeCheckConfig) -> BaseSessionService:
    """Construct the same Vertex session backend factory used by production."""

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        oga_env=RuntimeEnvironment.LOCAL,
        adk_session_backend="vertex_ai",
        google_cloud_project=config.project,
        google_cloud_region=config.location,
        adk_agent_engine_id=config.engine_id,
    )
    return create_session_service(settings)


async def close_session_service(service: BaseSessionService) -> None:
    close = getattr(service, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


def write_state(path: Path, state: RuntimeCheckState) -> None:
    path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def read_state(path: Path) -> RuntimeCheckState:
    if not path.is_file():
        raise ValueError(f"Runtime state file does not exist: {path}")
    return RuntimeCheckState.model_validate_json(path.read_text(encoding="utf-8"))


def require_matching_config(config: RuntimeCheckConfig, state: RuntimeCheckState) -> None:
    expected = (config.project, config.location, config.engine_id, config.app_name)
    actual = (state.project, state.location, state.engine_id, state.app_name)
    if actual != expected:
        raise ValueError("Runtime state does not match the current Agent Engine configuration")


def approval_calls(events: Sequence[Any]) -> list[Any]:
    return [
        part.function_call
        for event in events
        for part in (event.content.parts if event.content else [])
        if part.function_call and part.function_call.name == "adk_request_input"
    ]


async def pause_runtime(
    config: RuntimeCheckConfig,
    state_path: Path,
    *,
    service_factory: SessionServiceFactory = vertex_session_service,
) -> RuntimeCheckState:
    token = uuid4().hex
    state = RuntimeCheckState(
        project=config.project,
        location=config.location,
        engine_id=config.engine_id,
        app_name=config.app_name,
        user_id=f"runtime-check-{token}",
        session_id=f"runtime-check-{token}",
        invocation_id=f"runtime-check-{uuid4().hex}",
        created_at=datetime.now(UTC),
    )
    service = service_factory(config)
    try:
        if isinstance(service, VertexAiSessionService):
            await service.create_session(
                app_name=state.app_name,
                user_id=state.user_id,
                session_id=state.session_id,
                state={"runtime_check": token},
                ttl=RUNTIME_SESSION_TTL,
            )
        else:
            await service.create_session(
                app_name=state.app_name,
                user_id=state.user_id,
                session_id=state.session_id,
                state={"runtime_check": token},
            )
        write_state(state_path, state)
        print(f"created_session_id={state.session_id}", flush=True)
        print(f"created_invocation_id={state.invocation_id}", flush=True)

        calls = 0

        async def require_approval() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "summary": "Runtime check approval is required.",
                "has_pending_approvals": True,
                "has_clarifications": False,
                "has_safety_stops": False,
            }

        runner = Runner(
            app=build_site_update_app(
                state.app_name,
                require_approval,
                timeout_seconds=45,
            ),
            session_service=service,
        )
        events = [
            event
            async for event in runner.run_async(
                user_id=state.user_id,
                session_id=state.session_id,
                invocation_id=state.invocation_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text="Run the deterministic ADK runtime check.")],
                ),
            )
        ]
        requests = approval_calls(events)
        if calls != 1 or len(requests) != 1:
            raise RuntimeError(
                "ADK runtime did not reach exactly one approval interrupt "
                f"(node_calls={calls}, interrupts={len(requests)})"
            )
        approval_call = requests[0]
        if not approval_call.id or not approval_call.name:
            raise RuntimeError("ADK approval interrupt did not persist a callable identity")

        state = state.model_copy(
            update={
                "approval_call_id": approval_call.id,
                "approval_call_name": approval_call.name,
            }
        )
        write_state(state_path, state)
        persisted = await service.get_session(
            app_name=state.app_name,
            user_id=state.user_id,
            session_id=state.session_id,
        )
        if persisted is None or not persisted.events:
            raise RuntimeError("Paused ADK session or its event history was not persisted")

        print(f"workflow={AdkWorkflowId.DAILY_SITE_UPDATE}")
        print(f"session_id={state.session_id}")
        print(f"invocation_id={state.invocation_id}")
        print(f"approval_call_id={state.approval_call_id}")
        print(f"paused_event_count={len(persisted.events)}")
        print("ADK_RUNTIME_PAUSED=true")
        return state
    finally:
        await close_session_service(service)


async def resume_runtime(
    config: RuntimeCheckConfig,
    state_path: Path,
    *,
    service_factory: SessionServiceFactory = vertex_session_service,
) -> RuntimeCheckState:
    state = read_state(state_path)
    require_matching_config(config, state)
    if not state.approval_call_id or not state.approval_call_name:
        raise ValueError("Runtime state does not contain the paused approval call identity")

    service = service_factory(config)
    try:
        before = await service.get_session(
            app_name=state.app_name,
            user_id=state.user_id,
            session_id=state.session_id,
        )
        if before is None or not before.events:
            raise RuntimeError("Paused ADK session was not found after process replacement")

        calls = 0

        async def execute_after_approval() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "status": "completed",
                "has_pending_approvals": False,
                "has_clarifications": False,
                "has_safety_stops": False,
            }

        runner = Runner(
            app=build_site_update_app(
                state.app_name,
                execute_after_approval,
                timeout_seconds=45,
            ),
            session_service=service,
        )
        resumed_events = [
            event
            async for event in runner.run_async(
                user_id=state.user_id,
                session_id=state.session_id,
                invocation_id=state.invocation_id,
                new_message=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=state.approval_call_id,
                                name=state.approval_call_name,
                                response={"approval": "approved"},
                            )
                        )
                    ],
                ),
            )
        ]
        if calls != 1:
            raise RuntimeError(f"Resumed ADK action executed {calls} times; expected exactly once")
        if approval_calls(resumed_events):
            raise RuntimeError("Resumed ADK invocation requested approval again")
        if not resumed_events:
            raise RuntimeError("Resumed ADK invocation emitted no events")
        mismatched_invocations = {
            event.invocation_id
            for event in resumed_events
            if event.invocation_id and event.invocation_id != state.invocation_id
        }
        if mismatched_invocations:
            raise RuntimeError("ADK resume emitted events for a different invocation")

        persisted = await service.get_session(
            app_name=state.app_name,
            user_id=state.user_id,
            session_id=state.session_id,
        )
        if persisted is None:
            raise RuntimeError("Resumed ADK session was not persisted")
        if persisted.state.get("stage") != "completed":
            raise RuntimeError(
                "Resumed ADK workflow did not reach completed state: "
                f"{persisted.state.get('stage')!r}"
            )
        if set(persisted.state.get("branches_completed", [])) != {
            "progress",
            "blocker",
            "material",
        }:
            raise RuntimeError(
                "Persisted ADK state does not contain the completed fan-out branches"
            )

        print(f"session_id={state.session_id}")
        print(f"invocation_id={state.invocation_id}")
        print(f"resumed_event_count={len(resumed_events)}")
        print(f"persisted_event_count={len(persisted.events)}")
        print("resume_node_execution_count=1")
        print("ADK_RUNTIME_RESUMED=true")
        return state
    finally:
        await close_session_service(service)


async def cleanup_runtime(
    config: RuntimeCheckConfig,
    state_path: Path,
    *,
    service_factory: SessionServiceFactory = vertex_session_service,
) -> None:
    state = read_state(state_path)
    require_matching_config(config, state)
    service = service_factory(config)
    try:
        await service.delete_session(
            app_name=state.app_name,
            user_id=state.user_id,
            session_id=state.session_id,
        )
        for _ in range(5):
            remaining = await service.get_session(
                app_name=state.app_name,
                user_id=state.user_id,
                session_id=state.session_id,
            )
            if remaining is None:
                print(f"deleted_session_id={state.session_id}")
                print("ADK_SESSION_CLEANED=true")
                return
            await asyncio.sleep(1)
        raise RuntimeError("Temporary ADK runtime session still exists after deletion")
    finally:
        await close_session_service(service)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("pause", "resume", "cleanup"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--state-file", type=Path, required=True)
    return parser


async def run_phase(args: argparse.Namespace) -> None:
    config = load_runtime_config(args.env_file)
    if args.phase == "pause":
        await pause_runtime(config, args.state_file)
    elif args.phase == "resume":
        await resume_runtime(config, args.state_file)
    else:
        await cleanup_runtime(config, args.state_file)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(run_phase(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
