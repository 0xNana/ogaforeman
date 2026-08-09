"""Internal event publication API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.domain.events import ProjectEvent
from app.infrastructure.pubsub import PubSubClient, PubSubError


def create_event_router(publisher: PubSubClient | None = None) -> APIRouter:
    router = APIRouter(prefix="/events", tags=["events"])
    client = publisher or PubSubClient()

    @router.post("/", status_code=status.HTTP_202_ACCEPTED)
    async def receive_event(event: ProjectEvent) -> dict[str, str]:
        try:
            message_id = client.publish(
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


router = create_event_router()

__all__ = ["create_event_router", "router"]
