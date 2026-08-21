"""Review-first HTTP contract for project initialization imports."""

from __future__ import annotations

import asyncio
import base64
import binascii
from hashlib import sha256
from typing import Literal, cast

from fastapi import APIRouter, Query, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.api.limits import InMemoryRateLimiter
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.import_records import ProjectImportRecord
from app.domain.project_import import (
    DependencyDraft,
    ImportConflict,
    ImportWarning,
    MaterialDraft,
    MaterialRequirementDraft,
    MilestoneDraft,
    PhaseDraft,
    ProjectDraft,
    ProjectImportStatus,
    SourceType,
    TaskDraft,
)
from app.repositories.interfaces import VersionConflictError
from app.services.project_import_review import (
    ProjectImportDependencyUnavailableError,
    ProjectImportDraftExtractor,
    ProjectImportExtractionError,
    ProjectImportReviewNotFoundError,
    ProjectImportReviewResult,
    ProjectImportReviewService,
    ProjectImportReviewStateError,
)
from app.services.project_import_validation import ProjectImportValidationError
from app.services.project_import import (
    ProjectImportAlreadyCommittedError,
    ProjectImportConfirmationError,
)
from app.services.project_source_adapter import ProjectDocumentAdapter, StructuredTextInputError
from app.services.project_sources import ProjectSourceConflictError


router = APIRouter()


class CreateProjectImportRequest(BaseModel):
    """A bounded source accepted for review-only project initialization."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=500)
    source_text: str | None = Field(default=None, min_length=1, max_length=800_000)
    source_data_base64: str | None = Field(default=None, max_length=13_333_336)
    source_type: (
        Literal[
            SourceType.TEXT,
            SourceType.MARKDOWN,
            SourceType.FILE,
            SourceType.SPREADSHEET,
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_source_payload(self) -> "CreateProjectImportRequest":
        has_text = self.source_text is not None
        has_file = self.source_data_base64 is not None
        if has_text == has_file:
            raise ValueError("provide exactly one project source payload")
        if has_file and self.source_type not in {SourceType.FILE, SourceType.SPREADSHEET}:
            raise ValueError("file sources require a supported file source type")
        if has_text and self.source_type in {SourceType.FILE, SourceType.SPREADSHEET}:
            raise ValueError("file source types require encoded file content")
        return self


class ProjectImportDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class ProjectImportReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    status: ProjectImportStatus
    version: int
    project: ProjectDraft | None = None
    phases: list[PhaseDraft] = Field(default_factory=list)
    tasks: list[TaskDraft] = Field(default_factory=list)
    dependencies: list[DependencyDraft] = Field(default_factory=list)
    materials: list[MaterialDraft] = Field(default_factory=list)
    requirements: list[MaterialRequirementDraft] = Field(default_factory=list)
    milestones: list[MilestoneDraft] = Field(default_factory=list)
    warnings: list[ImportWarning] = Field(default_factory=list)
    conflicts: list[ImportConflict] = Field(default_factory=list)
    unresolved_references: list[str] = Field(default_factory=list)
    failure_code: str | None = None
    failure_message: str | None = None
    telemetry_trace_id: str | None = None
    prompt_registry_key: str | None = None
    model_registry_key: str | None = None
    diagnostic_stage: str | None = None
    diagnostic_attempt: int
    validation_outcome: str | None = None
    commit_outcome: str | None = None
    retryable: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    phase_count: int
    task_count: int
    material_count: int
    requirement_count: int
    replayed: bool = False


class ProjectImportSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    status: ProjectImportStatus
    version: int
    failure_code: str | None = None
    failure_message: str | None = None
    retryable: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    phase_count: int
    task_count: int
    material_count: int
    requirement_count: int


class ProjectImportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ProjectImportSummaryResponse]


def _review_service(
    request: Request,
    *,
    require_extractor: bool = False,
) -> ProjectImportReviewService:
    runtime = getattr(request.app.state, "auth_runtime", None)
    extractor = getattr(request.app.state, "project_import_draft_extractor", None)
    if runtime is None or not hasattr(runtime, "store"):
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    if require_extractor and (extractor is None or not hasattr(extractor, "extract")):
        raise ApiError(
            "DEPENDENCY_UNAVAILABLE",
            "Project import extraction is temporarily unavailable.",
            status_code=503,
        )
    return ProjectImportReviewService(
        runtime.store,
        cast(ProjectImportDraftExtractor, extractor) if extractor is not None else None,
    )


def _enforce_extraction_rate_limit(
    request: Request,
    access: ProjectAccessContext,
) -> None:
    limiter = getattr(request.app.state, "project_import_rate_limiter", None)
    if not isinstance(limiter, InMemoryRateLimiter):
        return
    limiter.check(
        user_id=access.actor.user_id,
        project_id=access.project_id,
        ip_address=request.client.host if request.client else None,
    )


def _response(result: ProjectImportReviewResult) -> ProjectImportReviewResponse:
    record = result.record
    draft = record.draft
    return ProjectImportReviewResponse(
        id=record.id,
        source_id=record.source_id,
        status=record.status,
        version=record.version,
        project=draft.project if draft is not None else None,
        phases=list(draft.phases) if draft is not None else [],
        tasks=list(draft.tasks) if draft is not None else [],
        dependencies=list(draft.dependencies) if draft is not None else [],
        materials=list(draft.materials) if draft is not None else [],
        requirements=list(draft.material_requirements) if draft is not None else [],
        milestones=list(draft.milestones) if draft is not None else [],
        warnings=list(draft.warnings) if draft is not None else [],
        conflicts=list(draft.conflicts) if draft is not None else [],
        unresolved_references=list(draft.unresolved_references) if draft is not None else [],
        failure_code=record.failure_code,
        failure_message=record.failure_message,
        telemetry_trace_id=record.telemetry_trace_id,
        prompt_registry_key=record.prompt_registry_key,
        model_registry_key=record.model_registry_key,
        diagnostic_stage=record.diagnostic_stage,
        diagnostic_attempt=record.diagnostic_attempt,
        validation_outcome=record.validation_outcome,
        commit_outcome=record.commit_outcome,
        retryable=_is_retryable(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
        phase_count=len(draft.phases) if draft is not None else record.phase_count,
        task_count=len(draft.tasks) if draft is not None else record.task_count,
        material_count=len(draft.materials) if draft is not None else record.material_count,
        requirement_count=(
            len(draft.material_requirements) if draft is not None else record.requirement_count
        ),
        replayed=result.replayed,
    )


def _summary(record: ProjectImportRecord) -> ProjectImportSummaryResponse:
    draft = record.draft
    return ProjectImportSummaryResponse(
        id=record.id,
        source_id=record.source_id,
        status=record.status,
        version=record.version,
        failure_code=record.failure_code,
        failure_message=record.failure_message,
        retryable=_is_retryable(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
        phase_count=len(draft.phases) if draft is not None else record.phase_count,
        task_count=len(draft.tasks) if draft is not None else record.task_count,
        material_count=len(draft.materials) if draft is not None else record.material_count,
        requirement_count=(
            len(draft.material_requirements) if draft is not None else record.requirement_count
        ),
    )


def _is_retryable(import_status: ProjectImportStatus) -> bool:
    return import_status in {
        ProjectImportStatus.EXTRACTION_FAILED,
        ProjectImportStatus.IMPORT_FAILED,
    }


def _import_id(project_id: str, idempotency_key: str) -> str:
    return _stable_id("imp", project_id, idempotency_key)


def _source_id(project_id: str, idempotency_key: str) -> str:
    return _stable_id("src", project_id, idempotency_key)


def _stable_id(prefix: str, project_id: str, idempotency_key: str) -> str:
    digest = sha256(f"{project_id}:|:{idempotency_key}".encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _not_found(exc: ProjectImportReviewNotFoundError) -> ApiError:
    return ApiError(exc.code, "Project import was not found.", status_code=404)


def _state_conflict(exc: RuntimeError) -> ApiError:
    code = getattr(exc, "code", "PROJECT_IMPORT_INVALID_STATE")
    return ApiError(
        code, "Project import is no longer in a valid state for that action.", status_code=409
    )


@router.post("", response_model=ProjectImportReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_import(
    project_id: str,
    payload: CreateProjectImportRequest,
    request: Request,
) -> ProjectImportReviewResponse:
    access = configured_project_access(request, project_id, ProjectPermission.MANAGE)
    idempotency_key = require_idempotency_key(request)
    import_id = _import_id(project_id, idempotency_key)
    service = _review_service(request)
    try:
        existing = service.get(access, import_id)
    except ProjectImportReviewNotFoundError:
        existing = None
    if existing is None or existing.status in {
        ProjectImportStatus.UPLOADED,
        ProjectImportStatus.EXTRACTION_FAILED,
    }:
        _enforce_extraction_rate_limit(request, access)
    try:
        source_text: str | None = payload.source_text
        source_type: SourceType | None = payload.source_type
        if payload.source_data_base64 is not None:
            try:
                source_data = base64.b64decode(payload.source_data_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise StructuredTextInputError("project file encoding is invalid") from exc
            if len(source_data) > ProjectDocumentAdapter.MAX_FILE_BYTES:
                raise StructuredTextInputError("project file exceeds the input limit")
            assert source_type in {SourceType.FILE, SourceType.SPREADSHEET}
            document = await asyncio.to_thread(
                ProjectDocumentAdapter(
                    name=payload.source_name,
                    source_type=source_type,
                ).load,
                source_data,
            )
            source_text = document.text
            source_type = document.source_type
        assert source_text is not None
        result = await service.extract_text(
            access,
            import_id=import_id,
            source_id=_source_id(project_id, idempotency_key),
            source_name=payload.source_name,
            source_text=source_text,
            source_type=source_type,
            extraction_idempotency_key=idempotency_key,
        )
    except StructuredTextInputError as exc:
        raise ApiError(exc.code, "Project source could not be accepted.", status_code=422) from exc
    except ProjectSourceConflictError as exc:
        raise ApiError(
            exc.code, "Idempotency key conflicts with another source.", status_code=409
        ) from exc
    except ProjectImportReviewStateError as exc:
        raise _state_conflict(exc) from exc
    except ProjectImportDependencyUnavailableError as exc:
        raise ApiError(
            exc.code,
            "Project import extraction is temporarily unavailable.",
            status_code=503,
        ) from exc
    except ProjectImportExtractionError as exc:
        raise ApiError(
            exc.code,
            "The extraction result could not be safely scoped to this import.",
            status_code=422,
        ) from exc
    except ProjectImportAlreadyCommittedError as exc:
        raise _state_conflict(exc) from exc
    return _response(result)


@router.get("", response_model=ProjectImportListResponse)
async def list_imports(
    project_id: str,
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    import_status: ProjectImportStatus | None = Query(default=None, alias="status"),
    nonterminal: bool = Query(default=False),
) -> ProjectImportListResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    records = _review_service(request).list(
        access,
        status=import_status,
        nonterminal=nonterminal,
        limit=limit,
    )
    return ProjectImportListResponse(data=[_summary(record) for record in records])


@router.get("/{import_id}", response_model=ProjectImportReviewResponse)
async def get_import(
    project_id: str,
    import_id: str,
    request: Request,
) -> ProjectImportReviewResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    try:
        record = _review_service(request).get(access, import_id)
    except ProjectImportReviewNotFoundError as exc:
        raise _not_found(exc) from exc
    return _response(ProjectImportReviewResult(record=record))


@router.post("/{import_id}/confirm", response_model=ProjectImportReviewResponse)
async def confirm_import(
    project_id: str,
    import_id: str,
    payload: ProjectImportDecisionRequest,
    request: Request,
) -> ProjectImportReviewResponse:
    access = configured_project_access(request, project_id, ProjectPermission.MANAGE)
    idempotency_key = require_idempotency_key(request)
    try:
        result = _review_service(request).confirm(
            access,
            import_id=import_id,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
    except ProjectImportReviewNotFoundError as exc:
        raise _not_found(exc) from exc
    except ProjectImportReviewStateError as exc:
        raise _state_conflict(exc) from exc
    except VersionConflictError as exc:
        raise ApiError(
            "PROJECT_IMPORT_VERSION_CONFLICT",
            "Project import changed; reload the review and try again.",
            status_code=409,
        ) from exc
    except ProjectImportAlreadyCommittedError as exc:
        raise _state_conflict(exc) from exc
    except ProjectImportConfirmationError as exc:
        raise ApiError(
            exc.code, "Project import confirmation is no longer valid.", status_code=409
        ) from exc
    except ProjectImportValidationError as exc:
        raise ApiError(
            "PROJECT_IMPORT_VALIDATION_FAILED",
            "Project import has validation conflicts that must be resolved first.",
            status_code=422,
        ) from exc
    return _response(result)


@router.post("/{import_id}/cancel", response_model=ProjectImportReviewResponse)
async def cancel_import(
    project_id: str,
    import_id: str,
    payload: ProjectImportDecisionRequest,
    request: Request,
) -> ProjectImportReviewResponse:
    access = configured_project_access(request, project_id, ProjectPermission.MANAGE)
    idempotency_key = require_idempotency_key(request)
    try:
        result = _review_service(request).cancel(
            access,
            import_id=import_id,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
    except ProjectImportReviewNotFoundError as exc:
        raise _not_found(exc) from exc
    except ProjectImportReviewStateError as exc:
        raise _state_conflict(exc) from exc
    except VersionConflictError as exc:
        raise ApiError(
            "PROJECT_IMPORT_VERSION_CONFLICT",
            "Project import changed; reload the review and try again.",
            status_code=409,
        ) from exc
    return _response(result)


__all__ = [
    "CreateProjectImportRequest",
    "ProjectImportDecisionRequest",
    "ProjectImportListResponse",
    "ProjectImportReviewResponse",
    "ProjectImportSummaryResponse",
    "router",
]
