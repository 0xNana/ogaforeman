"""Vendor-neutral trace/span helpers with safe correlation propagation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from secrets import token_hex
from time import monotonic
from types import TracebackType
from typing import Any

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


class TraceSpan:
    """A lightweight span that can be bridged to Cloud Trace later."""

    def __init__(self, name: str, *, trace_id: str | None = None, **attributes: Any) -> None:
        self.name = name
        self.trace_id = trace_id or current_context().trace_id or new_trace_id()
        self.span_id = f"spn_{token_hex(8)}"
        self.attributes = {key: str(value)[:256] for key, value in attributes.items()}
        self.started_at = datetime.now(UTC)
        self._started = monotonic()
        self.status = "ok"
        self.record: TraceRecord | None = None

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
        log_event(
            logging.getLogger("oga.trace"),
            logging.INFO if self.status == "ok" else logging.ERROR,
            "trace_span_finished",
            f"trace span {self.name} finished",
            status=self.status,
            duration_ms=round(duration_ms, 3),
        )
        self._scope.__exit__(exc_type, exc_value, traceback)


__all__ = ["TraceRecord", "TraceSpan", "new_trace_id"]
