"""Reusable FastAPI dependencies for request, auth, and mutation controls."""

from __future__ import annotations

from typing import Callable

from fastapi import Request
from pydantic import TypeAdapter, ValidationError

from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.models import IdempotencyKey

from .errors import ApiError, RequestContext, get_request_id
from .limits import InMemoryRateLimiter, RateLimitDecision


def require_idempotency_key(request: Request) -> str:
    value = request.headers.get("Idempotency-Key")
    if not value:
        raise ApiError(
            "VALIDATION_FAILED",
            "Idempotency-Key is required for mutations.",
            status_code=400,
        )
    try:
        return TypeAdapter(IdempotencyKey).validate_python(value)
    except ValidationError as exc:
        raise ApiError(
            "VALIDATION_FAILED",
            "Idempotency-Key is invalid.",
            status_code=400,
        ) from exc


def optional_idempotency_key(request: Request) -> str | None:
    value = request.headers.get("Idempotency-Key")
    if not value:
        return None
    return require_idempotency_key(request)


def request_context(
    request: Request,
    *,
    access: ProjectAccessContext | None = None,
    require_mutation_key: bool = False,
) -> RequestContext:
    key = (
        require_idempotency_key(request)
        if require_mutation_key
        else optional_idempotency_key(request)
    )
    return RequestContext(
        request_id=get_request_id(request),
        idempotency_key=key,
        user_id=access.actor.user_id if access else None,
        project_id=access.project_id if access else None,
    )


def configured_project_access(
    request: Request,
    project_id: str,
    permission: ProjectPermission = ProjectPermission.READ,
) -> ProjectAccessContext:
    provider = getattr(request.app.state, "project_access_provider", None)
    if provider is None:
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    access = provider(request, project_id, permission)
    if not isinstance(access, ProjectAccessContext):
        raise ApiError(
            "AUTH_PROJECT_FORBIDDEN", "Project access could not be established.", status_code=403
        )
    return access


def rate_limit_dependency(
    limiter: InMemoryRateLimiter,
    *,
    category: str = "general",
    cost: int = 1,
    access_provider: Callable[[Request], ProjectAccessContext | None] | None = None,
) -> Callable[[Request], RateLimitDecision]:
    def dependency(request: Request) -> RateLimitDecision:
        access = (
            access_provider(request)
            if access_provider
            else getattr(request.state, "project_access", None)
        )
        decision = limiter.check(
            user_id=access.actor.user_id if isinstance(access, ProjectAccessContext) else None,
            project_id=access.project_id if isinstance(access, ProjectAccessContext) else None,
            ip_address=request.client.host if request.client else None,
            cost=cost,
        )
        request.state.rate_limit_category = category
        request.state.rate_limit_decision = decision
        return decision

    return dependency


__all__ = [
    "configured_project_access",
    "optional_idempotency_key",
    "rate_limit_dependency",
    "request_context",
    "require_idempotency_key",
]
