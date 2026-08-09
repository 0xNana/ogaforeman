"""Vendor-neutral trace/span helpers with safe correlation propagation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from secrets import token_hex
from time import monotonic
from types import TracebackType
from typing import Any, Protocol, cast

from .context import bind_context, current_context
from .logging import log_event
import logging


def new_trace_id() -> str:
    return f"trc_{token_hex(16)}"


@dataclass(frozen=True, slots=True)
class TraceRecord:
    trace_id: str
    span_id: str
    name: str
    started_at: datetime
    duration_ms: float
    status: str
    attributes: dict[str, str]


class TraceClient(Protocol):
    def batch_write_spans(
        self,
        *,
        request: dict[str, object],
        retry: object,
        timeout: float,
    ) -> object: ...


class TraceExporter(Protocol):
    def export(self, record: TraceRecord) -> None: ...


class CloudTraceExporter:
    def __init__(self, project_id: str, *, client: TraceClient | None = None) -> None:
        if not project_id.strip():
            raise ValueError("project_id is required for Cloud Trace")
        self._project_id = project_id.strip()
        self._trace_client = client

    def export(self, record: TraceRecord) -> None:
        trace_id = cloud_trace_id(record.trace_id)
        span_id = cloud_span_id(record.span_id)
        attributes = {**record.attributes, "oga.status": record.status}
        span = {
            "name": (f"projects/{self._project_id}/traces/{trace_id}/spans/{span_id}"),
            "span_id": span_id,
            "display_name": {"value": record.name[:128]},
            "start_time": record.started_at,
            "end_time": record.started_at + timedelta(milliseconds=record.duration_ms),
            "attributes": {
                "attribute_map": {
                    key[:128]: {"string_value": {"value": value[:256]}}
                    for key, value in attributes.items()
                }
            },
        }
        self._client().batch_write_spans(
            request={"name": f"projects/{self._project_id}", "spans": [span]},
            retry=None,
            timeout=2.0,
        )

    def _client(self) -> TraceClient:
        if self._trace_client is None:
            from google.cloud import trace_v2

            self._trace_client = cast(TraceClient, trace_v2.TraceServiceClient())
        return self._trace_client


def cloud_trace_id(value: str) -> str:
    candidate = value.removeprefix("trc_").lower()
    if len(candidate) == 32 and all(character in "0123456789abcdef" for character in candidate):
        return candidate
    return sha256(value.encode("utf-8")).hexdigest()[:32]


def cloud_span_id(value: str) -> str:
    candidate = value.removeprefix("spn_").lower()
    if len(candidate) == 16 and all(character in "0123456789abcdef" for character in candidate):
        return candidate
    return sha256(value.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=8)
def cloud_trace_exporter(project_id: str) -> CloudTraceExporter:
    return CloudTraceExporter(project_id)


class TraceSpan:
    """A bounded span with an optional Cloud Trace export boundary."""

    def __init__(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        exporter: TraceExporter | None = None,
        **attributes: Any,
    ) -> None:
        self.name = name
        self.trace_id = trace_id or current_context().trace_id or new_trace_id()
        self.span_id = f"spn_{token_hex(8)}"
        self.attributes = {key: str(value)[:256] for key, value in attributes.items()}
        self.started_at = datetime.now(UTC)
        self._started = monotonic()
        self.status = "ok"
        self.record: TraceRecord | None = None
        self._exporter = exporter

    def __enter__(self) -> "TraceSpan":
        self._scope = bind_context(trace_id=self.trace_id)
        self._scope.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.status = "error"
        duration_ms = (monotonic() - self._started) * 1_000
        self.record = TraceRecord(
            trace_id=self.trace_id,
            span_id=self.span_id,
            name=self.name,
            started_at=self.started_at,
            duration_ms=duration_ms,
            status=self.status,
            attributes=self.attributes,
        )
        if self._exporter is not None:
            try:
                self._exporter.export(self.record)
            except Exception as exc:
                log_event(
                    logging.getLogger("oga.trace"),
                    logging.ERROR,
                    "trace_export_failed",
                    "trace export failed",
                    status="error",
                    error_code=type(exc).__name__,
                )
        log_event(
            logging.getLogger("oga.trace"),
            logging.INFO if self.status == "ok" else logging.ERROR,
            "trace_span_finished",
            f"trace span {self.name} finished",
            status=self.status,
            duration_ms=round(duration_ms, 3),
        )
        self._scope.__exit__(exc_type, exc_value, traceback)


__all__ = [
    "CloudTraceExporter",
    "TraceExporter",
    "TraceRecord",
    "TraceSpan",
    "cloud_span_id",
    "cloud_trace_exporter",
    "cloud_trace_id",
    "new_trace_id",
]
