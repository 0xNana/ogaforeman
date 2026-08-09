"""Project-scoped dead-letter inspection API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.observability.dead_letters import DeadLetterService


class DeadLetterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    attempts: int
    error_code: str | None
    error_summary: str | None
    dead_lettered_at: str


class DeadLetterList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[DeadLetterItem]
    count: int


def create_dead_letter_router(
    *,
    service_provider: Callable[[Request], DeadLetterService] | None = None,
    access_provider: Callable[[Request, str], ProjectAccessContext] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/projects/{project_id}/dead-letters", tags=["operations"])

    @router.get("", response_model=DeadLetterList)
    async def list_dead_letters(
        project_id: str,
        request: Request,
        limit: int = 100,
    ) -> DeadLetterList:
        service = (
            service_provider(request)
            if service_provider
            else getattr(request.app.state, "dead_letter_service", None)
        )
        if not isinstance(service, DeadLetterService):
            raise RuntimeError("dead-letter service is not configured")
        access = (
            access_provider(request, project_id)
            if access_provider
            else getattr(request.app.state, "project_access_provider", lambda *_: None)(
                request, project_id
            )
        )
        if not isinstance(access, ProjectAccessContext):
            raise PermissionError("project access context is required")
        ensure_project_scope(access, project_id)
        ensure_permission(access, ProjectPermission.READ)
        events = service.list(project_id, limit=limit)
        return DeadLetterList(
            data=[
                DeadLetterItem(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    attempts=event.attempts,
                    error_code=event.last_error_code,
                    error_summary=event.last_error_summary,
                    dead_lettered_at=event.dead_lettered_at.isoformat()
                    if event.dead_lettered_at
                    else "",
                )
                for event in events
            ],
            count=len(events),
        )

    return router


router = create_dead_letter_router()

__all__ = ["DeadLetterItem", "DeadLetterList", "create_dead_letter_router", "router"]
