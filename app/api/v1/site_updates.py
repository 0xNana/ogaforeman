from __future__ import annotations

from fastapi import APIRouter, Request, status
from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.enums import SiteUpdateInputType
from app.domain.authorization import ProjectPermission
from app.services.site_update_intake import (
    SiteUpdateAttachmentError,
    SiteUpdateIntakeService,
    SiteUpdatePublishError,
)


router = APIRouter()


class SiteUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    input_type: SiteUpdateInputType | None = None
    raw_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=1_000_000,
        validation_alias=AliasChoices("raw_text", "text"),
    )
    transcript: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=32)
    client_event_id: str | None = Field(default=None, min_length=1, max_length=256)
    occurred_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_site_evidence(self) -> "SiteUpdateRequest":
        if not self.raw_text and not self.transcript and not self.attachment_ids:
            raise ValueError("site update requires text, transcript, or attachments")
        if len(self.attachment_ids) != len(set(self.attachment_ids)):
            raise ValueError("attachment_ids cannot contain duplicates")
        return self


class SiteUpdateAcceptedResponse(BaseModel):
    site_update_id: str
    event_id: str
    agent_run_id: str
    status: str = "queued"
    status_url: str


@router.post(
    "",
    response_model=SiteUpdateAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_site_update(
    project_id: str,
    payload: SiteUpdateRequest,
    request: Request,
) -> SiteUpdateAcceptedResponse:
    service = getattr(request.app.state, "site_update_intake", None)
    if not isinstance(service, SiteUpdateIntakeService):
        raise ApiError(
            "DEPENDENCY_UNAVAILABLE",
            "Site updates are temporarily unavailable.",
            status_code=503,
        )
    access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
    try:
        result = service.submit(
            access,
            idempotency_key=require_idempotency_key(request),
            raw_text=payload.raw_text,
            transcript=payload.transcript,
            attachment_ids=payload.attachment_ids,
            input_type=payload.input_type,
            client_event_id=payload.client_event_id,
            occurred_at=payload.occurred_at,
        )
    except SiteUpdatePublishError as exc:
        raise ApiError(
            "SITE_UPDATE_SAVED_NOT_QUEUED",
            "Your update was saved, but Oga could not queue it yet. Retry safely.",
            status_code=503,
        ) from exc
    except SiteUpdateAttachmentError as exc:
        raise ApiError(
            exc.code,
            str(exc),
            status_code=422,
        ) from exc
    return SiteUpdateAcceptedResponse(
        site_update_id=result.site_update_id,
        event_id=result.event_id,
        agent_run_id=result.agent_run_id,
        status_url=(f"/api/v1/projects/{project_id}/agent-runs/{result.agent_run_id}"),
    )


__all__ = [
    "SiteUpdateAcceptedResponse",
    "SiteUpdateRequest",
    "router",
    "submit_site_update",
]
