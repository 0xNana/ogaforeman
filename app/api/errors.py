"""Stable HTTP error envelopes and request-ID middleware."""

from __future__ import annotations

import logging
import re
from contextlib import nullcontext
from time import monotonic
from dataclasses import dataclass
from secrets import token_hex
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ExceptionHandler

from app.domain.authorization import (
    AuthenticationRequiredError,
    ProjectForbiddenError,
    RoleRequiredError,
)
from app.domain.materials import MaterialUnitMismatchError, UnknownMaterialUnitError
from app.repositories.activity import ActivityIdempotencyConflict
from app.repositories.interfaces import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    VersionConflictError,
)
from app.services.attachments import (
    AttachmentConflictError,
    AttachmentError,
    AttachmentNotFoundError,
)
from app.services.tasks import (
    TaskApprovalRequiredError,
    TaskBlockedCompletionError,
    TaskDependencyIncompleteError,
    TaskEvidenceRejectedError,
    TaskMutationError,
    TaskStateError,
)

from .limits import RateLimitExceededError
from app.observability.context import bind_context, new_correlation_context
from app.observability.logging import log_event
from app.observability.metrics import metrics
from app.observability.tracing import TraceExporter, TraceSpan


logger = logging.getLogger("ogaforeman.api")
REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class ApiError(Exception):
    """An intentionally safe error that can be returned to an API client."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    idempotency_key: str | None = None
    user_id: str | None = None
    project_id: str | None = None


def new_request_id() -> str:
    return f"req_{token_hex(16)}"


def validate_request_id(value: str | None) -> str:
    if value is None or not value.strip():
        return new_request_id()
    candidate = value.strip()
    if not _REQUEST_ID_RE.fullmatch(candidate):
        raise ApiError(
            "VALIDATION_FAILED",
            "X-Request-ID must be an opaque request identifier.",
            status_code=400,
        )
    return candidate


def get_request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if isinstance(value, str) and value:
        return value
    value = validate_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = value
    return value


def error_response(error: ApiError, *, request_id: str) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=error.code,
            message=error.message,
            request_id=request_id,
            details=_safe_details(error.details),
        )
    )
    headers = {REQUEST_ID_HEADER: request_id, **error.headers}
    return JSONResponse(
        status_code=error.status_code,
        content=envelope.model_dump(mode="json"),
        headers=headers,
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            request_id = validate_request_id(request.headers.get(REQUEST_ID_HEADER))
        except ApiError as exc:
            request_id = new_request_id()
            request.state.request_id = request_id
            return error_response(exc, request_id=request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled request failure", extra={"request_id": request_id})
            raise
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def install_error_handlers(app: FastAPI) -> None:
    """Install stable handlers once on an application instance."""

    app.add_exception_handler(ApiError, cast(ExceptionHandler, _handle_api_error))
    app.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, _handle_validation_error),
    )
    app.add_exception_handler(HTTPException, cast(ExceptionHandler, _handle_http_error))
    app.add_exception_handler(
        VersionConflictError,
        cast(ExceptionHandler, _handle_unexpected_error),
    )
    app.add_exception_handler(Exception, cast(ExceptionHandler, _handle_unexpected_error))


def install_request_id_middleware(
    app: FastAPI,
    *,
    trace_exporter: TraceExporter | None = None,
) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        try:
            request_id = validate_request_id(request.headers.get(REQUEST_ID_HEADER))
        except ApiError as exc:
            request_id = new_request_id()
            request.state.request_id = request_id
            return error_response(exc, request_id=request_id)
        request.state.request_id = request_id
        started = monotonic()
        correlation = request.headers.get("X-Correlation-ID") or request_id
        trace_id = request.headers.get("X-Trace-ID")
        span_scope = (
            TraceSpan(
                "http.request",
                trace_id=trace_id,
                exporter=trace_exporter,
                method=request.method,
                route=request.url.path,
            )
            if trace_exporter is not None
            else nullcontext()
        )
        with (
            bind_context(
                new_correlation_context(
                    request_id=request_id,
                    correlation_id=correlation,
                    trace_id=trace_id,
                )
            ),
            span_scope,
        ):
            try:
                response = await call_next(request)
            except Exception:
                log_event(
                    logger,
                    logging.ERROR,
                    "http_request_failed",
                    "unhandled request failure",
                    method=request.method,
                    route=request.url.path,
                    status="error",
                )
                metrics.increment(
                    "http_requests_total",
                    labels={"method": request.method, "status_class": "5xx"},
                )
                raise
            duration = monotonic() - started
            status_class = f"{response.status_code // 100}xx"
            metrics.increment(
                "http_requests_total",
                labels={"method": request.method, "status_class": status_class},
            )
            metrics.observe(
                "http_request_duration_seconds",
                duration,
                labels={"method": request.method, "status_class": status_class},
            )
            log_event(
                logger,
                logging.INFO,
                "http_request_finished",
                "request finished",
                method=request.method,
                route=request.url.path,
                status=status_class,
                duration_ms=round(duration * 1_000, 3),
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Correlation-ID"] = correlation
        return response


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc, request_id=get_request_id(request))


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        ApiError(
            "VALIDATION_FAILED",
            "The request could not be validated.",
            status_code=400,
            details={"fields": _validation_fields(exc)},
        ),
        request_id=get_request_id(request),
    )


async def _handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code = {
        400: "VALIDATION_FAILED",
        401: "AUTH_REQUIRED",
        403: "AUTH_PROJECT_FORBIDDEN",
        404: "ENTITY_NOT_FOUND",
        409: "CONFLICT_VERSION_MISMATCH",
        413: "UPLOAD_TOO_LARGE",
        415: "MEDIA_TYPE_UNSUPPORTED",
        422: "VALIDATION_FAILED",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "DEPENDENCY_UNAVAILABLE",
    }.get(exc.status_code, "INTERNAL_ERROR")
    headers = {str(key): str(value) for key, value in (exc.headers or {}).items()}
    return error_response(
        ApiError(
            code,
            _safe_message(str(exc.detail), exc.status_code),
            status_code=exc.status_code,
            headers=headers,
        ),
        request_id=get_request_id(request),
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    mapped = map_exception(exc)
    if mapped.status_code >= 500:
        logger.exception(
            "request failed", exc_info=exc, extra={"request_id": get_request_id(request)}
        )
    return error_response(mapped, request_id=get_request_id(request))


def map_exception(exc: Exception) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, RateLimitExceededError):
        return ApiError(
            "RATE_LIMITED",
            "Too many requests. Please retry later.",
            status_code=429,
            details={"limit": exc.limit, "dimension": exc.dimension},
            headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, AuthenticationRequiredError):
        return ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    if isinstance(exc, ProjectForbiddenError):
        return ApiError(
            "AUTH_PROJECT_FORBIDDEN",
            "You do not have access to this project.",
            status_code=403,
        )
    if isinstance(exc, RoleRequiredError):
        return ApiError("ROLE_REQUIRED", "Your role cannot perform this action.", status_code=403)
    if isinstance(exc, (EntityNotFoundError, AttachmentNotFoundError)):
        return ApiError("ENTITY_NOT_FOUND", "The requested entity was not found.", status_code=404)
    if isinstance(exc, (VersionConflictError,)):
        return ApiError(
            "CONFLICT_VERSION_MISMATCH",
            "The entity changed; reload and retry with the current version.",
            status_code=409,
        )
    if isinstance(exc, (EntityAlreadyExistsError, ActivityIdempotencyConflict)):
        return ApiError(
            "DUPLICATE_IDEMPOTENCY_KEY",
            "This idempotency key has already been used for another mutation.",
            status_code=409,
        )
    if isinstance(exc, AttachmentError):
        message = str(exc)
        if "size" in message or "large" in message:
            return ApiError(
                "UPLOAD_TOO_LARGE", "The upload exceeds the allowed size.", status_code=413
            )
        if "content type" in message or "mime" in message or "type" in message:
            return ApiError(
                "MEDIA_TYPE_UNSUPPORTED", "The media type is not supported.", status_code=415
            )
        if isinstance(exc, AttachmentConflictError):
            return ApiError(
                "DUPLICATE_IDEMPOTENCY_KEY",
                "The attachment request conflicts with an existing upload.",
                status_code=409,
            )
        return ApiError(
            "VALIDATION_FAILED", "The attachment could not be accepted.", status_code=400
        )
    if isinstance(exc, (UnknownMaterialUnitError, MaterialUnitMismatchError)):
        return ApiError(
            "VALIDATION_FAILED",
            "The material unit is not valid for this material.",
            status_code=400,
        )
    if isinstance(exc, (TaskApprovalRequiredError,)):
        return ApiError(
            "APPROVAL_REQUIRED", "Human approval is required for this action.", status_code=422
        )
    if isinstance(
        exc,
        (
            TaskStateError,
            TaskBlockedCompletionError,
            TaskDependencyIncompleteError,
            TaskEvidenceRejectedError,
            TaskMutationError,
        ),
    ):
        code = getattr(exc, "code", "VALIDATION_FAILED")
        return ApiError(code, _safe_message(str(exc), 400), status_code=400)
    if isinstance(exc, PermissionError):
        return ApiError(
            "AUTH_PROJECT_FORBIDDEN", "You do not have access to this project.", status_code=403
        )
    if isinstance(exc, ValidationError | ValueError):
        return ApiError("VALIDATION_FAILED", "The request could not be accepted.", status_code=400)
    return ApiError("INTERNAL_ERROR", "An internal error occurred.", status_code=500)


def _validation_fields(exc: RequestValidationError) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        fields.append({"field": location or "request", "code": str(error.get("type", "invalid"))})
    return fields[:50]


def _safe_details(details: dict[str, Any]) -> dict[str, Any]:
    # Error details are deliberately shallow and scalar-oriented.  Never echo
    # arbitrary exception objects or request payloads into a public response.
    safe: dict[str, Any] = {}
    for key, value in details.items():
        if not isinstance(key, str) or len(key) > 100:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = [item for item in value[:50] if isinstance(item, (str, int, float, bool))]
    return safe


def _safe_message(message: str, status_code: int) -> str:
    if status_code >= 500:
        return "An internal error occurred."
    return message[:500]


__all__ = [
    "ApiError",
    "ErrorBody",
    "ErrorEnvelope",
    "REQUEST_ID_HEADER",
    "RequestContext",
    "RequestIdMiddleware",
    "error_response",
    "get_request_id",
    "install_error_handlers",
    "install_request_id_middleware",
    "map_exception",
    "new_request_id",
    "validate_request_id",
]
