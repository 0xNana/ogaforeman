"""JSON logging with an allowlisted, correlation-aware field set."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

from .context import current_context


_RESERVED = {
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "raw_text",
    "transcript",
    "photo",
    "audio",
    "body",
}
_ALLOWED_FIELDS = {
    "service",
    "environment",
    "event",
    "request_id",
    "correlation_id",
    "trace_id",
    "project_id",
    "event_id",
    "agent_run_id",
    "workflow",
    "step",
    "tool",
    "status",
    "duration_ms",
    "retry_attempt",
    "error_code",
    "dependency",
    "route",
    "method",
    "status_class",
}


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per line with no raw request payloads."""

    def format(self, record: logging.LogRecord) -> str:
        context = current_context()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "severity": record.levelname,
            "service": getattr(record, "service", None) or os.getenv("OGA_SERVICE", "oga-api"),
            "environment": getattr(record, "environment", None) or os.getenv("OGA_ENV", "local"),
            "event": getattr(record, "event", None) or record.name,
            "message": record.getMessage()[:1_000],
        }
        for field in (
            "request_id",
            "correlation_id",
            "trace_id",
            "project_id",
            "event_id",
            "agent_run_id",
            "workflow",
            "step",
            "tool",
            "retry_attempt",
        ):
            value = getattr(context, field)
            if value is not None:
                payload[field] = value

        for key, value in getattr(record, "oga_fields", {}).items():
            if key in _ALLOWED_FIELDS and key not in _RESERVED:
                payload[key] = _safe_value(value)

        if record.exc_info:
            error_type = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            payload["error_code"] = payload.get("error_code", error_type)
            payload["exception"] = str(record.exc_info[1])[:1_000]
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def configure_logging(*, stream: TextIO | None = None, level: int = logging.INFO) -> None:
    """Install the formatter once for the application process."""

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key in _ALLOWED_FIELDS and key not in _RESERVED
    }
    logger.log(level, message, extra={"event": event, "oga_fields": safe_fields})


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:1_000] if isinstance(value, str) else value
    return str(value)[:1_000]


__all__ = ["JsonLogFormatter", "configure_logging", "log_event"]
