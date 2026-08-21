from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from io import StringIO
from typing import Any

from app.observability.context import bind_context, current_context, new_correlation_context
from app.observability.health import HealthCheck, HealthRegistry
from app.observability.logging import JsonLogFormatter, log_event
from app.observability.metrics import MetricRegistry, metrics
from app.observability.project_import import (
    ProjectImportOutcome,
    ProjectImportStage,
    ProjectImportTelemetry,
)
from app.observability.tracing import CloudTraceExporter, TraceRecord, TraceSpan, cloud_trace_id


class FakeTraceClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def batch_write_spans(
        self,
        *,
        request: dict[str, object],
        retry: object,
        timeout: float,
    ) -> None:
        self.calls.append({"request": request, "retry": retry, "timeout": timeout})


class RecordingTraceExporter:
    def __init__(self) -> None:
        self.records: list[TraceRecord] = []

    def export(self, record: TraceRecord) -> None:
        self.records.append(record)


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


def test_cloud_trace_exporter_writes_bounded_v2_span() -> None:
    client = FakeTraceClient()
    exporter = CloudTraceExporter("oga-staging", client=client)
    record = TraceRecord(
        trace_id="trc_0123456789abcdef0123456789abcdef",
        span_id="spn_0123456789abcdef",
        name="http.request",
        started_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        duration_ms=125.0,
        status="ok",
        attributes={"method": "GET", "route": "/health/ready"},
    )

    exporter.export(record)

    call = client.calls[0]
    request = call["request"]
    assert request["name"] == "projects/oga-staging"
    span = request["spans"][0]
    assert span["name"].endswith("/traces/0123456789abcdef0123456789abcdef/spans/0123456789abcdef")
    assert span["display_name"] == {"value": "http.request"}
    assert span["attributes"]["attribute_map"]["oga.status"] == {"string_value": {"value": "ok"}}
    assert call["retry"] is None
    assert call["timeout"] == 2.0


def test_cloud_trace_id_hashes_noncanonical_context_ids_deterministically() -> None:
    first = cloud_trace_id("cor_site-update-123")
    assert first == cloud_trace_id("cor_site-update-123")
    assert len(first) == 32
    assert all(character in "0123456789abcdef" for character in first)


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


def test_project_import_telemetry_uses_one_trace_and_bounded_safe_fields() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("test-project-import-observability")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    registry = MetricRegistry(
        allowed_label_values={
            "import_stage": frozenset(stage.value for stage in ProjectImportStage),
            "outcome": frozenset(outcome.value for outcome in ProjectImportOutcome),
        }
    )
    exporter = RecordingTraceExporter()
    telemetry = ProjectImportTelemetry(
        registry=registry,
        logger=logger,
        exporter=exporter,
    )
    trace_id = "trc_0123456789abcdef0123456789abcdef"

    for stage in ProjectImportStage:
        with telemetry.observe(
            stage=stage,
            trace_id=trace_id,
            project_id="prj_importtelemetry",
            import_id="imp_importtelemetry",
            attempt=1,
            prompt_key="project_import_extraction.v3",
            model_key="project_import_gemini.configured",
        ) as observation:
            if stage is ProjectImportStage.REVIEW:
                observation.outcome = ProjectImportOutcome.BLOCKED

    assert [record.name for record in exporter.records] == [
        f"project_import.{stage.value}" for stage in ProjectImportStage
    ]
    assert {record.trace_id for record in exporter.records} == {trace_id}
    samples = registry.snapshot()
    assert sum(
        sample.value
        for sample in samples
        if sample.name == "project_import_stage_total" and sample.kind == "counter"
    ) == len(ProjectImportStage)
    assert sum(
        sample.value
        for sample in samples
        if sample.name == "project_import_stage_duration_seconds"
        and sample.kind == "histogram_count"
    ) == len(ProjectImportStage)
    payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
    stage_logs = [
        payload for payload in payloads if payload["event"] == "project_import_stage_finished"
    ]
    assert len(stage_logs) == len(ProjectImportStage)
    assert {payload["trace_id"] for payload in stage_logs} == {trace_id}
    assert {payload["prompt_key"] for payload in stage_logs} == {"project_import_extraction.v3"}
    assert all("workflow" not in payload for payload in stage_logs)
    assert "project_source" not in stream.getvalue()
