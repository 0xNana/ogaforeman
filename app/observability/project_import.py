"""Bounded telemetry for the durable project-import lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
import logging
from time import monotonic
from typing import Iterator

from app.observability.context import bind_context
from app.observability.logging import log_event
from app.observability.metrics import MetricRegistry, metrics
from app.observability.tracing import TraceExporter, TraceSpan


class ProjectImportStage(StrEnum):
    SOURCE = "source"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    REVIEW = "review"
    COMMIT = "commit"


class ProjectImportOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    REPLAYED = "replayed"


@dataclass(slots=True)
class ProjectImportObservation:
    outcome: ProjectImportOutcome = ProjectImportOutcome.SUCCEEDED
    error_code: str | None = None


class ProjectImportTelemetry:
    def __init__(
        self,
        *,
        registry: MetricRegistry = metrics,
        logger: logging.Logger | None = None,
        exporter: TraceExporter | None = None,
    ) -> None:
        self._registry = registry
        self._logger = logger or logging.getLogger("oga.project_import")
        self._exporter = exporter

    @contextmanager
    def observe(
        self,
        *,
        stage: ProjectImportStage,
        trace_id: str,
        project_id: str,
        import_id: str,
        attempt: int,
        prompt_key: str | None = None,
        model_key: str | None = None,
    ) -> Iterator[ProjectImportObservation]:
        observation = ProjectImportObservation()
        started = monotonic()
        with bind_context(
            trace_id=trace_id,
            project_id=project_id,
            event_id=import_id,
            step=stage.value,
            retry_attempt=attempt,
        ):
            try:
                with TraceSpan(
                    f"project_import.{stage.value}",
                    trace_id=trace_id,
                    exporter=self._exporter,
                    import_stage=stage.value,
                    prompt_key=prompt_key or "none",
                    model_key=model_key or "none",
                    retry_attempt=attempt,
                ) as span:
                    try:
                        yield observation
                    except Exception as exc:
                        observation.outcome = ProjectImportOutcome.FAILED
                        observation.error_code = _error_code(exc)
                        raise
                    finally:
                        span.attributes["outcome"] = observation.outcome.value
            finally:
                duration_seconds = monotonic() - started
                labels = {
                    "import_stage": stage.value,
                    "outcome": observation.outcome.value,
                }
                self._registry.increment("project_import_stage_total", labels=labels)
                self._registry.observe(
                    "project_import_stage_duration_seconds",
                    duration_seconds,
                    labels=labels,
                )
                log_event(
                    self._logger,
                    logging.ERROR
                    if observation.outcome is ProjectImportOutcome.FAILED
                    else logging.INFO,
                    "project_import_stage_finished",
                    "project import stage finished",
                    status=observation.outcome.value,
                    duration_ms=round(duration_seconds * 1_000, 3),
                    retry_attempt=attempt,
                    error_code=observation.error_code,
                    prompt_key=prompt_key,
                    model_key=model_key,
                    import_id=import_id,
                )


def _error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code[:128]
    return type(error).__name__[:128]


__all__ = [
    "ProjectImportObservation",
    "ProjectImportOutcome",
    "ProjectImportStage",
    "ProjectImportTelemetry",
]
