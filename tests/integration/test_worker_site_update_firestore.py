from __future__ import annotations

import os
from collections.abc import Mapping
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.agents.interpreter import FakeSiteInterpreter
from app.api.v1.router import api_router
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectPermission,
)
from app.domain.enums import (
    AgentRunStatus,
    ApprovalStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    ProcessingStatus,
    Severity,
    TaskStatus,
)
from app.domain.facts import (
    ExtractedFactSet,
    IssueFact,
    MaterialQuantityFact,
    NextFocusFact,
    TaskCompletionFact,
)
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    ProcessedEvent,
    SiteUpdate,
    Task,
)
from app.infrastructure.firestore import create_firestore_client
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.site_update_intake import SiteUpdateIntakeService
from app.worker import process_event_async
from scripts.reset_demo import reset_demo
from scripts.seed_demo import DEMO_FOREMAN_ID, DEMO_PROJECT_ID


UPDATE_TEXT = "First-floor blockwork is done. We have ten bags of cement left."
TRANSCRIPT = "Electrician did not come. Plastering is tomorrow."


class CapturingPublisher:
    def __init__(self) -> None:
        self.data: bytes | None = None
        self.calls = 0

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        del topic, attributes
        self.calls += 1
        self.data = data
        return "msg_firestore_worker123"


def _access_provider(
    request: object,
    project_id: str,
    permission: ProjectPermission = ProjectPermission.READ,
) -> ProjectAccessContext:
    del request
    assert project_id == DEMO_PROJECT_ID
    assert permission is ProjectPermission.OPERATE
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id=DEMO_FOREMAN_ID, subject="demo-foreman"),
        project_id=DEMO_PROJECT_ID,
        role=MemberRole.FOREMAN,
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for Firestore worker integration",
)
async def test_firestore_worker_executes_adk_site_update_and_suppresses_replay() -> None:
    emulator_host = os.environ["FIRESTORE_EMULATOR_HOST"]
    settings = Settings(
        _env_file=None,
        oga_env=RuntimeEnvironment.TEST,
        demo_mode=True,
        firestore_emulator_host=emulator_host,
        google_cloud_project="oga-foreman-worker-test",
        firestore_database="(default)",
    )
    client = create_firestore_client(settings)
    reset_demo(client, settings=settings)
    store = FirestoreRepositoryStore(client)
    publisher = CapturingPublisher()
    app = FastAPI()
    app.state.project_access_provider = _access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    payload = {
        "input_type": "mixed",
        "raw_text": UPDATE_TEXT,
        "transcript": TRANSCRIPT,
        "attachment_ids": ["att_demo001", "att_demo002"],
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_http:
        accepted_response = await client_http.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/site-updates",
            json=payload,
            headers={"Idempotency-Key": "firestore-worker-site-update-123"},
        )
        replay_response = await client_http.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/site-updates",
            json=payload,
            headers={"Idempotency-Key": "firestore-worker-site-update-123"},
        )
    assert accepted_response.status_code == 202
    assert replay_response.json() == accepted_response.json()
    accepted = accepted_response.json()
    assert publisher.data is not None
    assert publisher.calls == 1
    interpreter = FakeSiteInterpreter(
        responses={
            f"{UPDATE_TEXT} {TRANSCRIPT}": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="First-floor blockwork",
                        is_completed=True,
                        evidence="First-floor blockwork is done",
                        confidence="high",
                    )
                ],
                materials=[
                    MaterialQuantityFact(
                        material_name="cement bags",
                        quantity=10,
                        unit="bags",
                        evidence="We have ten bags of cement left",
                        confidence="high",
                    )
                ],
                issues=[
                    IssueFact(
                        issue_type=IssueType.BLOCKER,
                        task_name="Electrical rough-in",
                        description="Electrician did not come",
                        severity=Severity.HIGH,
                        evidence="Electrician did not come",
                        confidence="high",
                    )
                ],
                next_focus=[
                    NextFocusFact(
                        task_name="First-floor plastering",
                        description="Plastering is planned for tomorrow",
                        evidence="Plastering is tomorrow",
                        confidence="high",
                    )
                ],
            )
        }
    )

    first = await process_event_async(
        publisher.data,
        store=store,
        settings=settings,
        site_interpreter=interpreter,
    )
    replay = await process_event_async(
        publisher.data,
        store=store,
        settings=settings,
        site_interpreter=interpreter,
    )

    restarted = FirestoreRepositoryStore(create_firestore_client(settings))
    task = restarted.repository(Task).require(DEMO_PROJECT_ID, "tsk_blockwork")
    material = restarted.repository(Material).require(DEMO_PROJECT_ID, "mat_cement")
    update = restarted.repository(SiteUpdate).require(DEMO_PROJECT_ID, accepted["site_update_id"])
    run = restarted.repository(AgentRun).require(DEMO_PROJECT_ID, accepted["agent_run_id"])
    attachment = restarted.repository(Attachment).require(DEMO_PROJECT_ID, "att_demo001")
    second_attachment = restarted.repository(Attachment).require(DEMO_PROJECT_ID, "att_demo002")
    issues = restarted.repository(Issue).list(DEMO_PROJECT_ID)
    requests = restarted.repository(MaterialRequest).list(DEMO_PROJECT_ID)
    approvals = restarted.repository(Approval).list(DEMO_PROJECT_ID)
    reports = restarted.repository(DailyReport).list(DEMO_PROJECT_ID)
    activities = restarted.repository(ActivityEvent).list(DEMO_PROJECT_ID)

    assert first.result_ref == f"run:{accepted['agent_run_id']}"
    assert replay.status == "duplicate"
    assert interpreter.calls == [f"{UPDATE_TEXT} {TRANSCRIPT}"]
    assert task.status is TaskStatus.COMPLETED
    assert material.available_quantity == Decimal("10")
    assert update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
    assert run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert run.step == "approval_required"
    assert attachment.site_update_id == update.id
    assert second_attachment.site_update_id == update.id
    assert {(issue.type, tuple(issue.task_ids)) for issue in issues} == {
        (IssueType.BLOCKER, ("tsk_electrical",)),
        (IssueType.DELAY_RISK, ("tsk_plastering",)),
    }
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("30")
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert len(approvals) == 1
    assert approvals[0].id == requests[0].approval_id
    assert approvals[0].status is ApprovalStatus.PENDING
    assert len(reports) == 1
    assert reports[0].source_update_ids == [update.id]
    assert len(reports[0].completed_work) == 1
    assert len(reports[0].active_blockers) == 2
    assert len(reports[0].material_risks) == 1
    assert len(reports[0].next_focus) == 1
    assert len(restarted.repository(MaterialLedgerEntry).list(DEMO_PROJECT_ID)) == 1
    assert len(restarted.repository(ProcessedEvent).list(DEMO_PROJECT_ID)) == 1
    assert sum(activity.action == "issue.created" for activity in activities) == 2
    assert {activity.action for activity in activities} >= {
        "attachment.linked",
        "task.completed",
        "issue.created",
        "material.quantity_updated",
        "material.requested",
        "approval.requested",
        "report.projected",
        "site_update.approval_requested",
    }
