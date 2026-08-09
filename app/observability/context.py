"""Correlation identifiers shared by logs, traces, events, and workflow runs."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from secrets import token_hex
from typing import Iterator


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    request_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    project_id: str | None = None
    event_id: str | None = None
    agent_run_id: str | None = None
    workflow: str | None = None
    step: str | None = None
    tool: str | None = None
    retry_attempt: int | None = None


_CURRENT: ContextVar[CorrelationContext] = ContextVar(
    "oga_correlation_context", default=CorrelationContext()
)


def new_correlation_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    **fields: str | int | None,
) -> CorrelationContext:
    """Create a context with stable opaque IDs and bounded optional fields."""

    return CorrelationContext(
        request_id=request_id or f"req_{token_hex(12)}",
        correlation_id=correlation_id or f"cor_{token_hex(12)}",
        trace_id=trace_id or f"trc_{token_hex(16)}",
        project_id=_as_text(fields.get("project_id")),
        event_id=_as_text(fields.get("event_id")),
        agent_run_id=_as_text(fields.get("agent_run_id")),
        workflow=_as_text(fields.get("workflow")),
        step=_as_text(fields.get("step")),
        tool=_as_text(fields.get("tool")),
        retry_attempt=_as_int(fields.get("retry_attempt")),
    )


def current_context() -> CorrelationContext:
    return _CURRENT.get()


@contextmanager
def bind_context(
    context: CorrelationContext | None = None,
    **updates: str | int | None,
) -> Iterator[CorrelationContext]:
    """Bind a context for one request/event/workflow scope."""

    base = context or current_context()
    values: dict[str, str | int | None] = {
        field: getattr(base, field) for field in CorrelationContext.__dataclass_fields__
    }
    values.update(updates)
    bound = CorrelationContext(
        request_id=_as_text(values.get("request_id")),
        correlation_id=_as_text(values.get("correlation_id")),
        trace_id=_as_text(values.get("trace_id")),
        project_id=_as_text(values.get("project_id")),
        event_id=_as_text(values.get("event_id")),
        agent_run_id=_as_text(values.get("agent_run_id")),
        workflow=_as_text(values.get("workflow")),
        step=_as_text(values.get("step")),
        tool=_as_text(values.get("tool")),
        retry_attempt=_as_int(values.get("retry_attempt")),
    )
    token = _CURRENT.set(bound)
    try:
        yield bound
    finally:
        _CURRENT.reset(token)


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:256] if text else None


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


__all__ = ["CorrelationContext", "bind_context", "current_context", "new_correlation_context"]
