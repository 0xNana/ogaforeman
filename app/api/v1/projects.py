from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.authorization import AuthenticatedUser
from app.domain.enums import ProjectStatus
from app.domain.models import (
    ActivityEvent,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    Project,
    Task,
)

from .projections import project_snapshot_projection


router = APIRouter()


class ProjectResponse(BaseModel):
    id: str
    name: str
    location: str
    description: str | None
    status: str
    timezone: str
    start_date: date | None
    target_end_date: date | None


class ProjectListResponse(BaseModel):
    data: list[ProjectResponse]


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5_000)
    timezone: str = Field(min_length=1, max_length=100)
    start_date: date | None = None
    target_end_date: date | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def validate_dates(self) -> "CreateProjectRequest":
        if (
            self.start_date is not None
            and self.target_end_date is not None
            and self.target_end_date < self.start_date
        ):
            raise ValueError("target_end_date cannot be before start_date")
        return self


def project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        location=project.location,
        description=project.description,
        status=project.status.value.upper(),
        timezone=project.timezone,
        start_date=project.start_date,
        target_end_date=project.target_end_date,
    )


def auth_runtime(request: Request):
    runtime = getattr(request.app.state, "auth_runtime", None)
    if runtime is None:
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    return runtime


@router.get("", response_model=ProjectListResponse)
def list_projects(request: Request) -> ProjectListResponse:
    runtime = auth_runtime(request)
    actor = runtime.authenticate(request)
    if not isinstance(actor, AuthenticatedUser):
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    return ProjectListResponse(
        data=[project_response(item) for item in runtime.projects.list_for_user(actor)]
    )


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(payload: CreateProjectRequest, request: Request) -> ProjectResponse:
    runtime = auth_runtime(request)
    actor = runtime.authenticate(request)
    project = runtime.projects.create(
        actor,
        name=payload.name,
        location=payload.location,
        description=payload.description,
        timezone=payload.timezone,
        start_date=payload.start_date,
        target_end_date=payload.target_end_date,
        status=payload.status,
        idempotency_key=require_idempotency_key(request),
    )
    return project_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, request: Request) -> ProjectResponse:
    return project_response(
        auth_runtime(request).projects.require(configured_project_access(request, project_id))
    )


@router.get("/{project_id}/snapshot")
def get_project_snapshot(project_id: str, request: Request) -> dict[str, object]:
    runtime = auth_runtime(request)
    access = configured_project_access(request, project_id)
    project = runtime.projects.require(access)
    store = runtime.store
    member_names = _project_member_names(runtime, project_id, access.actor.user_id)
    return project_snapshot_projection(
        project,
        tasks=store.repository(Task).list(project_id),
        materials=store.repository(Material).list(project_id),
        material_requests=store.repository(MaterialRequest).list(project_id),
        approvals=store.repository(Approval).list(project_id),
        activities=store.repository(ActivityEvent).list(project_id),
        reports=store.repository(DailyReport).list(project_id),
        attachments=store.repository(Attachment).list(project_id),
        issues=store.repository(Issue).list(project_id),
        viewer_id=access.actor.user_id,
        member_names=member_names,
    )


def _project_member_names(runtime: object, project_id: str, viewer_id: str) -> dict[str, str]:
    resolver = getattr(runtime, "project_member_names", None)
    if callable(resolver):
        names = resolver(project_id)
        if isinstance(names, dict) and all(
            isinstance(member_id, str) and isinstance(display_name, str)
            for member_id, display_name in names.items()
        ):
            return names
    return {viewer_id: "You"}
