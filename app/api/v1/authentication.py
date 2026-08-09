from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.authorization import AuthenticatedUser

from ..errors import ApiError


router = APIRouter()


class BootstrapRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)


class BootstrapResponse(BaseModel):
    id: str
    email: str
    display_name: str


@router.post("/bootstrap", response_model=BootstrapResponse)
def bootstrap_identity(payload: BootstrapRequest, request: Request) -> BootstrapResponse:
    runtime = getattr(request.app.state, "auth_runtime", None)
    if runtime is None:
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    actor = runtime.authenticate(request, provision=True, display_name=payload.display_name)
    if not isinstance(actor, AuthenticatedUser) or not actor.email:
        raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
    return BootstrapResponse(
        id=actor.user_id,
        email=actor.email,
        display_name=payload.display_name or "Oga user",
    )
