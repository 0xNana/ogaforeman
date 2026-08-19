"""Authorized import-provenance explanations for canonical project facts."""

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import configured_project_access
from app.api.errors import ApiError
from app.domain.authorization import ProjectPermission
from app.domain.import_records import ImportProvenanceTargetType
from app.domain.models import CanonicalId
from app.domain.project_import import SourceType
from app.services.project_import_provenance import (
    ProjectImportProvenanceNotFoundError,
    ProjectImportProvenanceService,
)


router = APIRouter()


class ProjectImportProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: str
    source_id: str
    source_checksum: str
    source_type: SourceType
    source_name: str
    target_entity_type: ImportProvenanceTargetType
    target_entity_id: str
    section: str | None
    external_reference: str | None
    imported_by: str
    imported_at: datetime


def _runtime_service(request: Request) -> ProjectImportProvenanceService:
    runtime = getattr(request.app.state, "auth_runtime", None)
    if runtime is None or not hasattr(runtime, "store"):
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    return ProjectImportProvenanceService(runtime.store)


def _response(provenance: object) -> ProjectImportProvenanceResponse:
    return ProjectImportProvenanceResponse.model_validate(provenance, from_attributes=True)


def _not_found(exc: ProjectImportProvenanceNotFoundError) -> ApiError:
    return ApiError(exc.code, "Project import provenance was not found.", status_code=404)


@router.get("/records/{provenance_id}", response_model=ProjectImportProvenanceResponse)
async def get_provenance_record(
    project_id: str,
    provenance_id: CanonicalId,
    request: Request,
) -> ProjectImportProvenanceResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    try:
        provenance = _runtime_service(request).get(access, provenance_id)
    except ProjectImportProvenanceNotFoundError as exc:
        raise _not_found(exc) from exc
    return _response(provenance)


@router.get(
    "/dependencies/{predecessor_task_id}/{successor_task_id}",
    response_model=ProjectImportProvenanceResponse,
)
async def get_dependency_provenance(
    project_id: str,
    predecessor_task_id: CanonicalId,
    successor_task_id: CanonicalId,
    request: Request,
) -> ProjectImportProvenanceResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    try:
        provenance = _runtime_service(request).get_for_dependency(
            access,
            predecessor_task_id=predecessor_task_id,
            successor_task_id=successor_task_id,
        )
    except ProjectImportProvenanceNotFoundError as exc:
        raise _not_found(exc) from exc
    return _response(provenance)


@router.get(
    "/{target_entity_type}/{target_entity_id}",
    response_model=ProjectImportProvenanceResponse,
)
async def get_provenance(
    project_id: str,
    target_entity_type: ImportProvenanceTargetType,
    target_entity_id: CanonicalId,
    request: Request,
) -> ProjectImportProvenanceResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    try:
        provenance = _runtime_service(request).get_for_target(
            access,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
        )
    except ProjectImportProvenanceNotFoundError as exc:
        raise _not_found(exc) from exc
    return _response(provenance)


__all__ = ["ProjectImportProvenanceResponse", "router"]
