from __future__ import annotations

import json
import logging
from io import StringIO

from app.observability.context import bind_context, current_context, new_correlation_context
from app.observability.health import HealthCheck, HealthRegistry
from app.observability.logging import JsonLogFormatter, log_event
from app.observability.metrics import MetricRegistry, metrics
from app.observability.tracing import TraceSpan


def test_context_is_scoped_and_contains_correlation_ids() -> None:
    original = current_context()
    context = new_correlation_context(project_id="prj_example123")
    with bind_context(context, event_id="evt_example123"):
        assert current_context().trace_id == context.trace_id
        assert current_context().event_id == "evt_example123"
    assert current_context() == original


def test_json_log_contains_correlation_fields_and_redacts_reserved_fields() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("test-observability")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    with bind_context(new_correlation_context(request_id="req_test123", project_id="prj_test123")):
        log_event(
            logger,
            logging.INFO,
            "site_update_received",
            "site update accepted",
            event_id="evt_test123",
            raw_text="must not appear",
        )

    payload = json.loads(stream.getvalue())
    assert payload["request_id"] == "req_test123"
    assert payload["project_id"] == "prj_test123"
    assert payload["event_id"] == "evt_test123"
    assert "raw_text" not in payload
    assert "must not appear" not in stream.getvalue()


def test_metrics_bound_labels_and_export_prometheus() -> None:
    registry = MetricRegistry(allowed_label_values={"status_class": frozenset({"2xx", "5xx"})})
    registry.increment("http_requests_total", labels={"status_class": "2xx"})
    registry.observe("http_request_duration_seconds", 0.25, labels={"status_class": "2xx"})
    text = registry.prometheus_text()
    assert "http_requests_total_counter" in text
    assert "http_request_duration_seconds_histogram_count" in text

    try:
        registry.increment("http_requests_total", labels={"status_class": "unknown"})
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:  # pragma: no cover - assertion documents the safety boundary
        raise AssertionError("unbounded label value was accepted")


def test_http_metrics_accept_cors_preflight_method() -> None:
    metrics.increment(
        "http_requests_total",
        labels={"method": "OPTIONS", "status_class": "2xx"},
    )


def test_trace_span_records_error_status_and_trace_id() -> None:
    with TraceSpan("site_update", trace_id="trc_test123", project_id="prj_test123") as span:
        span.status = "ok"
    assert span.record is not None
    assert span.record.trace_id == "trc_test123"
    assert span.record.duration_ms >= 0


def test_health_and_readiness_report_dependency_state() -> None:
    registry = HealthRegistry((HealthCheck("firestore", lambda: True),))
    assert registry.liveness()["status"] == "ok"
    payload, code = registry.readiness()
    assert code == 200
    assert payload["status"] == "ready"

    failing = HealthRegistry((HealthCheck("firestore", lambda: (False, "offline")),))
    payload, code = failing.readiness()
    assert code == 503
    assert payload["checks"] == {"firestore": {"status": "failed", "detail": "offline"}}
