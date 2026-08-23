"""Cloud Run HTTP entrypoint for authenticated Pub/Sub and Scheduler delivery."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import UTC, datetime, time
from hashlib import sha256
from threading import Lock
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.agents.interpreter import SiteInterpreter
from app.api.errors import install_error_handlers, install_request_id_middleware
from app.api.health import create_runtime_health_router
from app.config.settings import Settings, get_settings
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.infrastructure.firestore import create_firestore_client
from app.infrastructure.pubsub import PubSubClient
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.interfaces import RepositoryStore
from app.worker import process_event_async


class PubSubPushMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: str = Field(min_length=1, max_length=15_000_000)
    message_id: str | None = Field(default=None, alias="messageId", max_length=256)


class PubSubPushEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: PubSubPushMessage
    subscription: str = Field(min_length=1, max_length=1_000)


class DailyBriefScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: str
    timezone: str


def create_worker_app(
    *,
    settings: Settings | None = None,
    store: RepositoryStore | None = None,
    publisher: PubSubClient | None = None,
    site_interpreter: SiteInterpreter | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    runtime = settings or get_settings()
    application = FastAPI(title="OG Foreman Worker", version=runtime.app_version)
    application.state.settings = runtime
    application.state.store = store
    application.state.publisher = publisher
    application.state.site_interpreter = site_interpreter
    application.state.composition_lock = Lock()
    now = clock or (lambda: datetime.now(UTC))

    install_request_id_middleware(application)
    install_error_handlers(application)
    application.include_router(create_runtime_health_router(runtime))

    @application.post("/pubsub/push", status_code=status.HTTP_204_NO_CONTENT)
    async def pubsub_push(envelope: PubSubPushEnvelope) -> Response:
        _validate_subscription(runtime, envelope.subscription)
        try:
            event_data = base64.b64decode(envelope.message.data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=400, detail="Pub/Sub message data is invalid") from exc
        if not event_data:
            raise HTTPException(status_code=400, detail="Pub/Sub message data is empty")
        await process_event_async(
            event_data,
            store=_store(application, runtime),
            settings=runtime,
            site_interpreter=application.state.site_interpreter,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.post("/scheduler/daily-brief", status_code=status.HTTP_202_ACCEPTED)
    async def schedule_daily_brief(request: DailyBriefScheduleRequest) -> dict[str, str]:
        try:
            timezone = ZoneInfo(request.timezone)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="timezone must be a valid IANA zone"
            ) from exc
        current = now().astimezone(UTC)
        report_date = current.astimezone(timezone).date()
        window_start = datetime.combine(report_date, time.min, tzinfo=timezone).astimezone(UTC)
        event_key = f"daily-brief:{request.project_id}:{report_date.isoformat()}"
        digest = sha256(event_key.encode("utf-8")).hexdigest()
        event = ProjectEvent(
            event_id=f"evt_{digest[:24]}",
            project_id=request.project_id,
            event_type=EventType.DAILY_BRIEF_REQUESTED,
            source=EventSource.SCHEDULER,
            occurred_at=window_start,
            received_at=window_start,
            actor=EventActor(type=EventActorType.WORKLOAD, id="wrk_scheduler"),
            idempotency_key=event_key,
            correlation_id=f"cor_{digest[24:48]}",
            payload={"report_date": report_date.isoformat(), "timezone": request.timezone},
        )
        message_id = _publisher(application, runtime).publish(
            None,
            event.model_dump_json().encode("utf-8"),
            attributes={
                "event_type": event.event_type.value,
                "project_id": event.project_id,
                "schema_version": event.schema_version,
            },
        )
        return {"status": "accepted", "message_id": message_id, "event_id": event.event_id}

    return application


def _store(application: FastAPI, settings: Settings) -> RepositoryStore:
    current = application.state.store
    if current is not None:
        return current
    with application.state.composition_lock:
        current = application.state.store
        if current is None:
            current = FirestoreRepositoryStore(create_firestore_client(settings))
            application.state.store = current
    return current


def _publisher(application: FastAPI, settings: Settings) -> PubSubClient:
    current = application.state.publisher
    if isinstance(current, PubSubClient):
        return current
    with application.state.composition_lock:
        current = application.state.publisher
        if not isinstance(current, PubSubClient):
            current = PubSubClient(settings)
            application.state.publisher = current
    return current


def _validate_subscription(settings: Settings, delivered_subscription: str) -> None:
    expected = settings.pubsub_worker_subscription
    if expected and delivered_subscription.rsplit("/", maxsplit=1)[-1] != expected:
        raise HTTPException(status_code=403, detail="Pub/Sub subscription is not authorized")


app = create_worker_app()


__all__ = [
    "DailyBriefScheduleRequest",
    "PubSubPushEnvelope",
    "PubSubPushMessage",
    "app",
    "create_worker_app",
]
