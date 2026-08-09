from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.activity import MutationContext
from app.domain.authorization import ProjectPermission
from app.domain.enums import ActorType
from app.services.approvals import ApprovalService, ResolutionCommand

from .projections import approval_projection

router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str | None = Field(default=None, max_length=5_000)
    expected_version: int = Field(ge=0)


@router.post("/{approval_id}/decision")
def resolve_approval(
    project_id: str,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
) -> dict[str, object]:
    access = configured_project_access(request, project_id, ProjectPermission.APPROVE)
    runtime = getattr(request.app.state, "auth_runtime", None)
    if runtime is None:
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    occurred_at = datetime.now(UTC)
    command = ResolutionCommand(
        project_id=project_id,
        approval_id=approval_id,
        notes=payload.notes,
        expected_version=payload.expected_version,
        occurred_at=occurred_at,
    )
    context = MutationContext(
        project_id=project_id,
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key=require_idempotency_key(request),
        occurred_at=occurred_at,
    )
    service = ApprovalService(runtime.store)
    result = (
        service.approve(access, command, context)
        if payload.decision == "approved"
        else service.reject(access, command, context)
    )
    project = runtime.projects.require(access)
    return approval_projection(result.approval, ZoneInfo(project.timezone))
