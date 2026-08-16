from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import configured_project_access
from app.domain.authorization import ProjectPermission
from app.domain.enums import AgentRunStatus, WorkflowName
from app.domain.models import AgentRun


router = APIRouter()


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    project_id: str
    trigger_event_id: str
    workflow: WorkflowName
    status: AgentRunStatus
    step: str | None
    attempt: int
    trace_id: str
    adk_session_id: str | None
    adk_invocation_id: str | None
    adk_workflow_id: str | None
    started_at: datetime
    updated_at: datetime
    result_summary: str | None
    pending_actions: list[str]
    error_code: str | None
    error_summary: str | None
    completed_at: datetime | None


@router.get("/{run_id}", response_model=AgentRunResponse)
def get_agent_run(
    project_id: str,
    run_id: str,
    request: Request,
) -> AgentRunResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    run = request.app.state.auth_runtime.store.repository(AgentRun).require(
        access.project_id,
        run_id,
    )
    return AgentRunResponse(
        id=run.id,
        run_id=run.id,
        project_id=run.project_id,
        trigger_event_id=run.trigger_event_id,
        workflow=run.workflow,
        status=run.status,
        step=run.step,
        attempt=run.attempt,
        trace_id=run.trace_id,
        adk_session_id=run.adk_session_id,
        adk_invocation_id=run.adk_invocation_id,
        adk_workflow_id=run.adk_workflow_id,
        started_at=run.started_at,
        updated_at=run.updated_at,
        result_summary=run.result_summary,
        pending_actions=run.pending_actions,
        error_code=run.error_code,
        error_summary=run.error_summary,
        completed_at=run.completed_at,
    )


__all__ = ["AgentRunResponse", "get_agent_run", "router"]
