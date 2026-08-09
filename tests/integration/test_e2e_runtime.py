from __future__ import annotations

import os
from decimal import Decimal

import httpx
import pytest

from app.domain.enums import (
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    IssueType,
    MaterialRequestStatus,
    OutboxStatus,
    TaskStatus,
)
from app.domain.events import EventType
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    SiteUpdate,
    Task,
)
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.memory import InMemoryRepositoryStore
from scripts.run_e2e_api import ACTOR_ID, PROJECT_ID, create_app


AUTH_HEADERS = {
    "Authorization": "Bearer local-e2e-token",
    "Idempotency-Key": "playwright:site-update:production-path",
}
UPDATE_TEXT = (
    "First-floor blockwork is complete. The electrician did not come today. "
    "We have 10 bags of cement left. Plastering starts tomorrow."
)


@pytest.mark.asyncio
async def test_e2e_api_uses_production_worker_and_resumes_the_same_run() -> None:
    app = create_app()
    runtime = app.state.auth_runtime
    store = runtime.store
    expected_store_type = (
        FirestoreRepositoryStore
        if os.getenv("FIRESTORE_EMULATOR_HOST")
        else InMemoryRepositoryStore
    )
    assert isinstance(store, expected_store_type)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/site-updates",
            json={"input_type": "text", "raw_text": UPDATE_TEXT},
            headers=AUTH_HEADERS,
        )
        replay = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/site-updates",
            json={"input_type": "text", "raw_text": UPDATE_TEXT},
            headers=AUTH_HEADERS,
        )

        assert accepted.status_code == 202, accepted.text
        assert replay.status_code == 202, replay.text
        assert replay.json() == accepted.json()

        accepted_body = accepted.json()
        run_id = accepted_body["agent_run_id"]
        run_before_approval = store.repository(AgentRun).require(PROJECT_ID, run_id)
        assert run_before_approval.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert run_before_approval.step == "approval_required"
        assert run_before_approval.result_summary is not None
        assert "Electrical rough-in is blocked" in run_before_approval.result_summary
        assert any(
            "schedule impact on First-floor plastering" in action
            for action in run_before_approval.pending_actions
        )

        assert len(store.repository(SiteUpdate).list(PROJECT_ID)) == 1
        task = store.repository(Task).require(PROJECT_ID, "tsk_blockwork123")
        assert task.status is TaskStatus.COMPLETED
        assert task.completion_percent == Decimal("100")
        cement = store.repository(Material).require(PROJECT_ID, "mat_cement123")
        assert cement.available_quantity == Decimal("10")

        issues = store.repository(Issue).list(PROJECT_ID)
        assert {(issue.type, tuple(issue.task_ids)) for issue in issues} >= {
            (IssueType.BLOCKER, ("tsk_electrical123",)),
            (IssueType.DELAY_RISK, ("tsk_plastering123",)),
        }
        assert len(issues) == 3
        requests = store.repository(MaterialRequest).list(PROJECT_ID)
        assert len(requests) == 1
        material_request = requests[0]
        assert material_request.status is MaterialRequestStatus.AWAITING_APPROVAL
        assert material_request.quantity == Decimal("30")

        approvals = [
            approval
            for approval in store.repository(Approval).list(PROJECT_ID)
            if approval.action_type is ApprovalActionType.PURCHASE
        ]
        assert len(approvals) == 1
        approval = approvals[0]
        assert approval.id == material_request.approval_id
        assert approval.status is ApprovalStatus.PENDING

        decided = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/approvals/{approval.id}/decision",
            json={
                "decision": "approved",
                "expected_version": approval.version,
                "notes": "Approved for tomorrow's plastering.",
            },
            headers={
                "Authorization": "Bearer local-e2e-token",
                "Idempotency-Key": "playwright:approval:production-path",
            },
        )

    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"

    resumed_run = store.repository(AgentRun).require(PROJECT_ID, run_id)
    assert resumed_run.status is AgentRunStatus.COMPLETED
    assert resumed_run.id == run_before_approval.id
    submitted_request = store.repository(MaterialRequest).require(
        PROJECT_ID,
        material_request.id,
    )
    assert submitted_request.status is MaterialRequestStatus.SUBMITTED

    activities = store.repository(ActivityEvent).list(PROJECT_ID)
    dynamic_actions = {
        activity.action
        for activity in activities
        if activity.agent_run_id == run_id or activity.entity_id == approval.id
    }
    assert {
        "site_update.received",
        "site_update.media_processed",
        "site_update.interpreted",
        "project.context_retrieved",
        "site_update.processing_started",
        "task.completed",
        "issue.created",
        "blocker.detected",
        "schedule.risk_detected",
        "material.quantity_updated",
        "material.risk_detected",
        "material.requested",
        "approval.requested",
        "report.projected",
        "report.updated",
        "site_update.approval_requested",
        "workflow.paused",
        "approval.approved",
        "workflow.resumed",
        "external_action.executed",
        "workflow.completed",
    } <= dynamic_actions
    required_once = {
        "site_update.received",
        "site_update.media_processed",
        "site_update.interpreted",
        "project.context_retrieved",
        "task.completed",
        "blocker.detected",
        "material.quantity_updated",
        "material.risk_detected",
        "material.requested",
        "approval.requested",
        "report.updated",
        "workflow.paused",
        "approval.approved",
        "workflow.resumed",
        "external_action.executed",
        "workflow.completed",
    }
    for action in required_once:
        assert (
            sum(
                activity.action == action and activity.agent_run_id == run_id
                for activity in activities
            )
            == 1
        ), action
    for activity in activities:
        if activity.agent_run_id == run_id and activity.action in required_once | {
            "schedule.risk_detected"
        }:
            assert activity.agent_run_id == run_id
            assert activity.source_event_id is not None
            serialized_metadata = str(activity.metadata).casefold()
            assert "chain_of_thought" not in serialized_metadata
            assert "raw_prompt" not in serialized_metadata
            assert UPDATE_TEXT.casefold() not in serialized_metadata
    assert (
        sum(
            activity.action == "material_request.submitted"
            and activity.entity_id == material_request.id
            for activity in activities
        )
        == 1
    )

    continuation_messages = [
        message
        for message in store.repository(OutboxMessage).list(PROJECT_ID)
        if message.message_type == EventType.APPROVAL_GRANTED.value
    ]
    assert len(continuation_messages) == 1
    assert continuation_messages[0].status is OutboxStatus.COMPLETED
    assert continuation_messages[0].attempts == 1
    assert store.repository(Approval).require(PROJECT_ID, approval.id).resolved_by == ACTOR_ID
    assert [result.route for result in runtime.event_transport.worker_results] == [
        "site_report",
        "materials",
    ]
    assert len(runtime.interpreter.fact_calls) == 1
    assert '"id":"tsk_electrical123"' in runtime.interpreter.fact_calls[0][2]
