"""Idempotent event worker entrypoint."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError

from app.agents.coordinator import OgaCoordinator, coordinator
from app.agents.interpreter import SiteInterpreter
from app.agents.site_update_execution import EventPayloadMismatchError, SiteUpdateEventExecutor
from app.config.settings import Settings, get_settings
from app.domain.authorization import ProjectForbiddenError, RoleRequiredError
from app.domain.events import EventType, ProjectEvent
from app.infrastructure.gemini import GeminiSiteInterpreter
from app.observability.context import bind_context, new_correlation_context
from app.observability.logging import log_event
from app.observability.metrics import metrics
from app.observability.tracing import TraceSpan
from app.repositories.interfaces import EntityNotFoundError, RepositoryStore
from app.services.event_claims import ClaimOutcome, EventClaimService, InvalidEventClaim
from app.services.external_actions import ExternalActionService
from app.services.routed_events import RoutedEventExecutor
from app.services.site_update_lifecycle import InvalidSiteUpdateTransition
from app.workflows.resume import ResumeWorkflow
from app.workflows.runtime import RuntimeManager


logger = logging.getLogger("ogaforeman.worker")


@dataclass(frozen=True, slots=True)
class WorkerResult:
    event_id: str
    status: str
    route: str | None = None
    result_ref: str | None = None


async def process_event_async(
    event_data: bytes,
    *,
    store: RepositoryStore,
    event_coordinator: OgaCoordinator = coordinator,
    settings: Settings | None = None,
    site_interpreter: SiteInterpreter | None = None,
) -> WorkerResult:
    """Validate, claim, route, and finalize one at-least-once event delivery."""

    runtime = settings or get_settings()

    try:
        event = ProjectEvent.model_validate_json(event_data)
    except ValidationError:
        metrics.increment("worker_invalid_events_total")
        log_event(
            logger,
            logging.ERROR,
            "event_validation_failed",
            "event envelope validation failed",
            status="rejected",
            error_code="EVENT_VALIDATION_FAILED",
        )
        raise

    context = new_correlation_context(
        correlation_id=event.correlation_id,
        trace_id=str(event.metadata.get("trace_id") or event.correlation_id),
        project_id=event.project_id,
        event_id=event.event_id,
    )
    claims = EventClaimService(
        store,
        lease_seconds=runtime.event_claim_lease_seconds,
        max_attempts=runtime.event_claim_max_attempts,
    )
    with (
        bind_context(context),
        TraceSpan(
            "worker.process_event",
            trace_id=context.trace_id,
            event_type=event.event_type.value,
        ),
    ):
        claim = claims.claim(event)
        if claim.outcome is ClaimOutcome.DUPLICATE_COMPLETED:
            metrics.increment("worker_duplicate_events_total")
            log_event(
                logger,
                logging.INFO,
                "event_duplicate_suppressed",
                "duplicate event returned its prior result",
                status="duplicate",
            )
            return WorkerResult(
                event_id=event.event_id,
                status="duplicate",
                result_ref=claim.result_ref,
            )
        if claim.outcome is ClaimOutcome.BUSY:
            metrics.increment("worker_busy_events_total")
            return WorkerResult(event_id=event.event_id, status="busy")
        if claim.outcome is ClaimOutcome.DEAD_LETTERED:
            metrics.increment("worker_dead_letter_events_total")
            return WorkerResult(event_id=event.event_id, status="dead_lettered")
        if claim.claim_token is None:
            raise RuntimeError("acquired event claim did not include an owner token")

        try:
            result = event_coordinator.process_event(event)
            route = str(result["route_decision"])
            result_ref = f"route:{route}:event:{event.event_id}"
            if event.event_type is EventType.SITE_UPDATE_RECEIVED:
                interpreter = site_interpreter or GeminiSiteInterpreter(runtime)
                execution = await SiteUpdateEventExecutor(
                    store,
                    interpreter,
                    runtime,
                ).execute(
                    event,
                    claim_attempt=claim.attempts,
                )
                result_ref = f"run:{execution['run_id']}"
            elif event.event_type is EventType.APPROVAL_GRANTED:
                continuation = ResumeWorkflow(store).handle_approval_granted(
                    event.project_id,
                    str(event.payload["approval_id"]),
                    str(event.payload["resolver"]),
                )
                delay_event = ExternalActionService(store).continue_approved_purchase(event)
                if delay_event is not None:
                    await process_event_async(
                        delay_event.model_dump_json().encode(),
                        store=store,
                        event_coordinator=event_coordinator,
                        settings=runtime,
                        site_interpreter=site_interpreter,
                    )
                RuntimeManager(store).complete_run(event.project_id, continuation.run_id)
                result_ref = f"run:{continuation.run_id}"
            elif event.event_type is EventType.APPROVAL_REJECTED:
                ResumeWorkflow(store).handle_approval_rejected(
                    event.project_id,
                    str(event.payload["approval_id"]),
                    str(event.payload["resolver"]),
                )
            else:
                routed_execution = RoutedEventExecutor(store).execute(event)
                result_ref = routed_execution.result_ref
            claims.complete(event, claim_token=claim.claim_token, result_ref=result_ref)
        except Exception as exc:
            try:
                claims.fail(
                    event,
                    claim_token=claim.claim_token,
                    error_code=type(exc).__name__[:128],
                    error_summary=str(exc)[:5_000] or "worker event processing failed",
                    terminal=isinstance(
                        exc,
                        (
                            EntityNotFoundError,
                            EventPayloadMismatchError,
                            InvalidSiteUpdateTransition,
                            ProjectForbiddenError,
                            RoleRequiredError,
                        ),
                    ),
                )
            except InvalidEventClaim:
                logger.exception("event claim ownership expired before failure persistence")
            metrics.increment(
                "worker_events_total",
                labels={"workflow": _workflow_label(event), "status_class": "5xx"},
            )
            log_event(
                logger,
                logging.ERROR,
                "event_processing_failed",
                "event processing failed",
                status="failed",
                error_code=type(exc).__name__,
            )
            raise

        metrics.increment(
            "worker_events_total",
            labels={"workflow": _workflow_label(event), "status_class": "2xx"},
        )
        log_event(
            logger,
            logging.INFO,
            "event_processing_completed",
            "event processing completed",
            status="completed",
            workflow=_workflow_label(event),
        )
        return WorkerResult(
            event_id=event.event_id,
            status="completed",
            route=route,
            result_ref=result_ref,
        )


def process_event(
    event_data: bytes,
    *,
    store: RepositoryStore,
    event_coordinator: OgaCoordinator = coordinator,
    settings: Settings | None = None,
    site_interpreter: SiteInterpreter | None = None,
) -> WorkerResult:
    """Compatibility wrapper; production HTTP delivery uses ``process_event_async``."""

    coroutine = process_event_async(
        event_data,
        store=store,
        event_coordinator=event_coordinator,
        settings=settings,
        site_interpreter=site_interpreter,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="oga-worker-sync") as executor:
        return executor.submit(asyncio.run, coroutine).result()


def _workflow_label(event: ProjectEvent) -> str:
    route = coordinator.route_event(event)
    return {
        "site_report": "daily_site_update",
        "materials": "material_shortage",
        "planner": "blocker_delay",
        "communicator": "daily_brief",
    }[route]


__all__ = [
    "EventPayloadMismatchError",
    "WorkerResult",
    "process_event",
    "process_event_async",
]
