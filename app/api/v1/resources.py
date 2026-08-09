from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.dependencies import configured_project_access, require_idempotency_key
from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.enums import ActorType, TaskPriority
from app.services.materials import CreateMaterialCommand, MaterialService
from app.services.tasks import CreateTaskCommand, TaskService

from .projects import auth_runtime
from .projections import material_projection, task_projection


router = APIRouter()


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    priority: TaskPriority = TaskPriority.MEDIUM


class CreateMaterialRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=100)
    available_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_required_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    upcoming_requirement_quantity: Decimal | None = Field(default=None, ge=0)


def mutation_context(
    request: Request, project_id: str
) -> tuple[ProjectAccessContext, MutationContext]:
    access = configured_project_access(request, project_id, ProjectPermission.MANAGE)
    return access, MutationContext(
        project_id=project_id,
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key=require_idempotency_key(request),
    )


@router.post("/{project_id}/tasks", status_code=201)
def create_task(project_id: str, payload: CreateTaskRequest, request: Request) -> dict[str, object]:
    access, context = mutation_context(request, project_id)
    task = (
        TaskService(auth_runtime(request).store)
        .create_task(
            access,
            CreateTaskCommand(project_id=project_id, **payload.model_dump()),
            context,
        )
        .task
    )
    timezone = ZoneInfo(auth_runtime(request).projects.require(access).timezone)
    return task_projection(task, timezone)


@router.post("/{project_id}/materials", status_code=201)
def create_material(
    project_id: str, payload: CreateMaterialRequest, request: Request
) -> dict[str, object]:
    access, context = mutation_context(request, project_id)
    material = (
        MaterialService(auth_runtime(request).store)
        .create_material(
            access,
            CreateMaterialCommand(project_id=project_id, **payload.model_dump()),
            context,
        )
        .material
    )
    return material_projection(material, None)


__all__ = ["router"]
