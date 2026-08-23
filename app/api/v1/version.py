"""Public, non-secret deployment provenance endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.config.settings import Settings


class VersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_version: str
    git_sha: str | None
    build_timestamp: AwareDatetime | None
    source_tree_dirty: bool
    environment: str
    service: str | None
    revision: str | None


router = APIRouter()


@router.get("/version", response_model=VersionResponse)
async def get_version(request: Request, response: Response) -> VersionResponse:
    response.headers["Cache-Control"] = "no-store"
    settings: Settings = request.app.state.settings
    return VersionResponse(
        app_version=settings.app_version,
        git_sha=settings.app_git_sha,
        build_timestamp=settings.app_build_time,
        source_tree_dirty=settings.app_source_tree_dirty,
        environment=settings.oga_env.value,
        service=settings.k_service,
        revision=settings.k_revision,
    )


__all__ = ["VersionResponse", "router"]
