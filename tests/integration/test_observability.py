from __future__ import annotations

import json
import logging
from io import StringIO
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_request_id_middleware
from app.api.health import router as health_router
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import MemberRole
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.project_import import ProjectImportDraft, ProjectImportStatus, SourceType
from app.observability.dead_letters import DeadLetterService
from app.observability.logging import JsonLogFormatter
from app.observability.metrics import MetricRegistry
from app.observability.project_import import (
    ProjectImportOutcome,
    ProjectImportStage,
    ProjectImportTelemetry,
)
from app.observability.tracing import TraceRecord
from app.repositories.memory import InMemoryRepositoryStore
from app.services.event_claims import EventClaimService
from app.services.project_import_review import ProjectImportReviewService


class RecordingTraceExporter:
    def __init__(self) -> None:
        self.records: list[TraceRecord] = []

    def export(self, record: TraceRecord) -> None:
        self.records.append(record)


class TraceableImportExtractor:
    async def extract(self, **values: Any) -> ProjectImportDraft:
        return ProjectImportDraft(
            id=values["import_id"],
            project_id=values["project_id"],
            source_id=values["source_id"],
            status=ProjectImportStatus.NEEDS_REVIEW,
            project={"name": "Trace House"},
        )


@pytest.mark.asyncio
async def test_request_logs_and_response_share_request_and_correlation_ids() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("ogaforeman.api")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    app = FastAPI()
    install_request_id_middleware(app)
    app.include_router(health_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health/live",
            headers={"X-Request-ID": "req_health123", "X-Correlation-ID": "cor_health123"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req_health123"
    assert response.headers["X-Correlation-ID"] == "cor_health123"
    record = json.loads(stream.getvalue())
    assert record["request_id"] == "req_health123"
    assert record["correlation_id"] == "cor_health123"
    assert record["event"] == "http_request_finished"


def test_dead_letter_inspection_is_project_scoped_and_redacts_claim_tokens() -> None:
    store = InMemoryRepositoryStore()
    claims = EventClaimService(store, max_attempts=1)
    now = "2026-08-08T10:00:00+00:00"
    event = ProjectEvent(
        event_id="evt_deadletter123",
        project_id="prj_deadletter123",
        event_type=EventType.SITE_UPDATE_RECEIVED,
        source=EventSource.WEB,
        occurred_at=now,
        received_at=now,
        actor=EventActor(type=EventActorType.USER, id="usr_foreman123"),
        idempotency_key="dead-letter:123",
        correlation_id="cor_deadletter123",
        payload={
            "site_update_id": "sup_deadletter123",
            "text": "Blockwork is complete.",
            "transcript": None,
            "attachment_ids": [],
        },
    )
    claimed = claims.claim(event)
    assert claimed.claim_token is not None
    claims.fail(
        event,
        claim_token=claimed.claim_token,
        error_code="TEST_FAILURE",
        error_summary="deliberate test failure",
    )

    service = DeadLetterService(store)
    events = service.list("prj_deadletter123")
    assert len(events) == 1
    assert events[0].claim_token is None
    assert service.list("prj_otherproject123") == ()


@pytest.mark.asyncio
async def test_project_import_trace_and_diagnostics_span_extraction_through_commit() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("test-project-import-integration")
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
    telemetry = ProjectImportTelemetry(registry=registry, logger=logger, exporter=exporter)
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_importobserver", subject="import-observer"),
        project_id="prj_importobserver",
        role=MemberRole.ADMIN,
    )
    service = ProjectImportReviewService(
        store,
        TraceableImportExtractor(),
        telemetry=telemetry,
    )
    trace_id = "trc_0123456789abcdef0123456789abcdef"

    extracted = await service.extract_text(
        access,
        import_id="imp_importobserver",
        source_id="src_importobserver",
        source_name="trace-house.md",
        source_text="CONFIDENTIAL TRACE HOUSE SOURCE",
        source_type=SourceType.MARKDOWN,
        extraction_idempotency_key="project-import-observer",
        trace_id=trace_id,
    )
    confirmed = service.confirm(
        access,
        import_id=extracted.record.id,
        expected_version=extracted.record.version,
        idempotency_key="project-import-observer-confirm",
    )

    assert confirmed.record.status is ProjectImportStatus.IMPORTED
    assert confirmed.record.telemetry_trace_id == trace_id
    assert confirmed.record.prompt_registry_key == "project_import_extraction.v1"
    assert confirmed.record.model_registry_key == "project_import_gemini.configured"
    assert confirmed.record.diagnostic_stage == "commit"
    assert confirmed.record.validation_outcome == "succeeded"
    assert confirmed.record.commit_outcome == "succeeded"
    assert {record.name for record in exporter.records} == {
        f"project_import.{stage.value}" for stage in ProjectImportStage
    }
    assert {record.trace_id for record in exporter.records} == {trace_id}
    assert "CONFIDENTIAL TRACE HOUSE SOURCE" not in stream.getvalue()
