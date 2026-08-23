"""Internal event publication API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, status

from app.domain.events import EventType, ProjectEvent
from app.infrastructure.pubsub import PubSubClient, PubSubError


def create_event_router(
    publisher: PubSubClient,
    *,
    authorize: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(prefix="/events", tags=["events"])

    @router.post("/", status_code=status.HTTP_202_ACCEPTED)
    async def receive_event(event: ProjectEvent, request: Request) -> dict[str, str]:
        authorize(request)
        if event.event_type is EventType.DELIVERY_DELAYED:
            raise HTTPException(
                status_code=400,
                detail="delivery delays require the authenticated project intake",
            )
        try:
            message_id = publisher.publish(
                None,
                event.model_dump_json().encode("utf-8"),
                attributes={
                    "event_type": event.event_type.value,
                    "project_id": event.project_id,
                    "schema_version": event.schema_version,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PubSubError as exc:
            raise HTTPException(status_code=503, detail="event transport is unavailable") from exc
        return {"status": "accepted", "message_id": message_id}

    return router


__all__ = ["create_event_router"]
