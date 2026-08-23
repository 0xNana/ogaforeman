"""Authenticated operator boundary for external delivery-delay reports."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.authorization import ProjectPermission
from app.services.delivery_delay_intake import (
    DeliveryDelayIntakeService,
    DeliveryDelayPublishError,
)


router = APIRouter()


class DeliveryDelayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material_request_id: str = Field(min_length=1, max_length=256)
    revised_delivery_date: date
    reason: str = Field(min_length=1, max_length=2_000)
    occurred_at: AwareDatetime | None = None


class DeliveryDelayAcceptedResponse(BaseModel):
    event_id: str
    status: str = "queued"


@router.post(
    "",
    response_model=DeliveryDelayAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_delivery_delay(
    project_id: str,
    payload: DeliveryDelayRequest,
    request: Request,
) -> DeliveryDelayAcceptedResponse:
    service = getattr(request.app.state, "delivery_delay_intake", None)
    if not isinstance(service, DeliveryDelayIntakeService):
        raise ApiError(
            "DEPENDENCY_UNAVAILABLE",
            "Delivery-delay intake is temporarily unavailable.",
            status_code=503,
        )
    access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
    try:
        result = service.submit(
            access,
            material_request_id=payload.material_request_id,
            revised_delivery_date=payload.revised_delivery_date,
            reason=payload.reason,
            occurred_at=payload.occurred_at,
            idempotency_key=require_idempotency_key(request),
        )
    except DeliveryDelayPublishError as exc:
        raise ApiError(
            "DELIVERY_DELAY_SAVED_NOT_QUEUED",
            "The delay was saved but could not be queued. Retry safely.",
            status_code=503,
        ) from exc
    except ValueError as exc:
        raise ApiError("VALIDATION_FAILED", str(exc), status_code=422) from exc
    return DeliveryDelayAcceptedResponse(event_id=result.event_id)


__all__ = [
    "DeliveryDelayAcceptedResponse",
    "DeliveryDelayRequest",
    "router",
    "submit_delivery_delay",
]
