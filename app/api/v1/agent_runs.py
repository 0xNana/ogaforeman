from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import configured_project_access
from app.domain.authorization import ProjectPermission
from app.domain.enums import AgentRunStatus
from app.domain.models import AgentRun


router = APIRouter()


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: AgentRunStatus
    step: str | None
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
        status=run.status,
        step=run.step,
        error_code=run.error_code,
        error_summary=run.error_summary,
        completed_at=run.completed_at,
    )


__all__ = ["AgentRunResponse", "get_agent_run", "router"]
