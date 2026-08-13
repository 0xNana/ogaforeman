from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.authorization import ProjectAccessContext
from app.services.attachments import (
    AttachmentError,
    AttachmentInput,
    AttachmentNotFoundError,
    AttachmentService,
    AttachmentConflictError,
)


Sha256 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-fA-F0-9]{64}$"),
]


class SignUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    attachment_id: str | None = Field(default=None, min_length=3, max_length=128)
    original_name: str | None = Field(default=None, max_length=500)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    sha256: Sha256


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str
    project_id: str
    object_path: str
    upload_url: str
    expires_at: datetime
    required_headers: dict[str, str]
    max_bytes: int


class VerifyUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str
    project_id: str
    object_path: str
    content_type: str
    byte_size: int
    sha256: str
    upload_status: str
    read_url: str | None = None
    read_url_expires_at: datetime | None = None


def create_upload_router(
    *,
    service_provider: Callable[[Request], AttachmentService] | None = None,
    access_provider: Callable[[Request, str], ProjectAccessContext] | None = None,
) -> APIRouter:
    """Build the versioned upload router with explicit application dependencies."""

    router = APIRouter(prefix="/api/v1")

    def service(request: Request) -> AttachmentService:
        if service_provider is not None:
            return service_provider(request)
        configured = getattr(request.app.state, "attachment_service", None)
        if not isinstance(configured, AttachmentService):
            raise RuntimeError("attachment service is not configured")
        return configured

    def access(request: Request, project_id: str) -> ProjectAccessContext:
        if access_provider is not None:
            return access_provider(request, project_id)
        configured = getattr(request.app.state, "project_access_provider", None)
        if configured is not None:
            return configured(request, project_id)
        configured_access = getattr(request.state, "project_access", None)
        if isinstance(configured_access, ProjectAccessContext):
            return configured_access
        raise RuntimeError("project access context is not configured")

    @router.post(
        "/projects/{project_id}/uploads/sign",
        response_model=UploadResponse,
        status_code=201,
    )
    def sign_upload(
        project_id: str,
        payload: SignUploadRequest,
        request: Request,
        upload_service: AttachmentService = Depends(service),
    ) -> UploadResponse | JSONResponse:
        try:
            grant = upload_service.sign_upload(
                access(request, project_id),
                AttachmentInput.model_validate(payload.model_dump()),
                project_id=project_id,
            )
        except PermissionError as exc:
            return _permission_error(exc)
        except AttachmentError as exc:
            return _error(exc)
        return UploadResponse(
            attachment_id=grant.attachment.id,
            project_id=grant.attachment.project_id,
            object_path=grant.attachment.object_path,
            upload_url=grant.signed_upload.url,
            expires_at=grant.signed_upload.expires_at,
            required_headers=grant.signed_upload.required_headers,
            max_bytes=grant.max_bytes,
        )

    @router.post(
        "/projects/{project_id}/uploads/{attachment_id}/verify",
        response_model=VerifyUploadResponse,
    )
    def verify_upload(
        project_id: str,
        attachment_id: str,
        request: Request,
        include_read_url: bool = False,
        upload_service: AttachmentService = Depends(service),
    ) -> VerifyUploadResponse | JSONResponse:
        try:
            result = upload_service.verify_upload(
                access(request, project_id),
                attachment_id,
                project_id=project_id,
                include_read_url=include_read_url,
            )
        except PermissionError as exc:
            return _permission_error(exc)
        except AttachmentNotFoundError as exc:
            return _error(exc, status_code=404)
        except AttachmentConflictError as exc:
            return _error(exc, status_code=409)
        except AttachmentError as exc:
            return _error(exc)
        read = result.signed_read
        return VerifyUploadResponse(
            attachment_id=result.attachment.id,
            project_id=result.attachment.project_id,
            object_path=result.attachment.object_path,
            content_type=result.attachment.content_type,
            byte_size=result.attachment.byte_size,
            sha256=result.attachment.sha256,
            upload_status=result.attachment.upload_status.value,
            read_url=read.url if read else None,
            read_url_expires_at=read.expires_at if read else None,
        )

    @router.get(
        "/projects/{project_id}/uploads/{attachment_id}/read-url",
        response_model=VerifyUploadResponse,
    )
    def read_url(
        project_id: str,
        attachment_id: str,
        request: Request,
        upload_service: AttachmentService = Depends(service),
    ) -> VerifyUploadResponse | JSONResponse:
        try:
            result = upload_service.get_read_url(
                access(request, project_id),
                attachment_id,
                project_id=project_id,
            )
        except PermissionError as exc:
            return _permission_error(exc)
        except AttachmentNotFoundError as exc:
            return _error(exc, status_code=404)
        except AttachmentConflictError as exc:
            return _error(exc, status_code=409)
        except AttachmentError as exc:
            return _error(exc)
        read = result.signed_read
        return VerifyUploadResponse(
            attachment_id=result.attachment.id,
            project_id=result.attachment.project_id,
            object_path=result.attachment.object_path,
            content_type=result.attachment.content_type,
            byte_size=result.attachment.byte_size,
            sha256=result.attachment.sha256,
            upload_status=result.attachment.upload_status.value,
            read_url=read.url if read else None,
            read_url_expires_at=read.expires_at if read else None,
        )

    return router


def _error(exc: AttachmentError, *, status_code: int = 422) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


def _permission_error(exc: PermissionError) -> JSONResponse:
    code = getattr(exc, "code", "AUTH_PROJECT_FORBIDDEN")
    return JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": str(exc)}},
    )


router = create_upload_router()

__all__ = [
    "SignUploadRequest",
    "UploadResponse",
    "VerifyUploadResponse",
    "create_upload_router",
    "router",
]
