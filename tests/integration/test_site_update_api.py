from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.agents.interpreter import FakeSiteInterpreter
from app.api.v1.router import api_router
from app.config.settings import Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import (
    AgentRunStatus,
    ApprovalStatus,
    AttachmentUploadStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
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
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.site_update_intake import SiteUpdateAttachmentError, SiteUpdateIntakeService
from app.worker import process_event


class WorkerPublisher:
    def __init__(
        self,
        store: InMemoryRepositoryStore,
        interpreter: FakeSiteInterpreter | None = None,
    ) -> None:
        self._store = store
        self._interpreter = interpreter or FakeSiteInterpreter()
        self.published_event_ids: list[str] = []

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: dict[str, str] | None = None,
    ) -> str:
        del topic, attributes
        result = process_event(
            data,
            store=self._store,
            settings=Settings(_env_file=None),
            site_interpreter=self._interpreter,
        )
        self.published_event_ids.append(result.event_id)
        return f"msg_{result.event_id}"


def access_provider(
    request: object,
    project_id: str,
    permission: ProjectPermission = ProjectPermission.READ,
) -> ProjectAccessContext:
    del request
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman123", subject="sub_foreman123"),
        project_id="prj_readiness123",
        role=MemberRole.FOREMAN,
    )
    if project_id != access.project_id:
        raise ValueError("cross-project access")
    assert permission is ProjectPermission.OPERATE
    return access


@pytest.mark.asyncio
async def test_site_update_is_persisted_audited_published_and_started_once() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_readiness123",
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    publisher = WorkerPublisher(store)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/projects/prj_readiness123/site-updates",
            json={"raw_text": "Blockwork is complete."},
            headers={"Idempotency-Key": "readiness:site-update:123"},
        )
        replay = await client.post(
            "/api/v1/projects/prj_readiness123/site-updates",
            json={"raw_text": "Blockwork is complete."},
            headers={"Idempotency-Key": "readiness:site-update:123"},
        )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == first.json()
    response = first.json()
    assert response["status"] == "queued"
    assert response["status_url"].endswith(response["agent_run_id"])
    assert len(store.repository(SiteUpdate).list("prj_readiness123")) == 1
    activities = store.repository(ActivityEvent).list("prj_readiness123")
    assert {activity.action for activity in activities} == {
        "report.projected",
        "site_update.received",
        "site_update.processing_started",
        "site_update.processing_completed",
    }
    assert len(store.repository(OutboxMessage).list("prj_readiness123")) == 1
    run = store.repository(AgentRun).require(
        "prj_readiness123",
        response["agent_run_id"],
    )
    assert run.status is AgentRunStatus.COMPLETED
    assert publisher.published_event_ids == [response["event_id"]]


@pytest.mark.asyncio
async def test_mixed_api_update_persists_complete_daily_site_update_projection() -> None:
    project_id = "prj_readiness123"
    update_text = "First-floor blockwork is done. We have ten bags of cement left."
    transcript = "Electrician did not come. Plastering is tomorrow."
    interpreter = FakeSiteInterpreter(
        responses={
            f"{update_text} {transcript}": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="First-floor blockwork",
                        is_completed=True,
                        evidence="First-floor blockwork is done",
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
                materials=[
                    MaterialQuantityFact(
                        material_name="cement bags",
                        quantity=10,
                        unit="bags",
                        evidence="We have ten bags of cement left",
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
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    for task in (
        Task(
            id="tsk_blockwork123",
            project_id=project_id,
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        ),
        Task(
            id="tsk_electrical123",
            project_id=project_id,
            title="Electrical rough-in",
            status=TaskStatus.PLANNED,
            dependency_ids=["tsk_blockwork123"],
        ),
        Task(
            id="tsk_plastering123",
            project_id=project_id,
            title="First-floor plastering",
            status=TaskStatus.PLANNED,
            dependency_ids=["tsk_blockwork123"],
        ),
    ):
        store.repository(Task).create(task)
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=project_id,
            name="Cement Bags",
            normalized_name="cement bags",
            aliases=["cement"],
            unit="bags",
            available_quantity=Decimal("25"),
            minimum_required_quantity=Decimal("20"),
            upcoming_requirement_quantity=Decimal("40"),
            estimated_unit_cost=Decimal("12.50"),
        )
    )
    store.repository(Attachment).create(
        Attachment(
            id="att_progress123",
            project_id=project_id,
            object_path=f"projects/{project_id}/attachments/att_progress123",
            content_type="image/jpeg",
            byte_size=512,
            sha256="a" * 64,
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    publisher = WorkerPublisher(store, interpreter)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")

    request = {
        "input_type": "mixed",
        "raw_text": update_text,
        "transcript": transcript,
        "attachment_ids": ["att_progress123"],
        "occurred_at": datetime(2026, 8, 8, 9, 30, tzinfo=UTC).isoformat(),
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json=request,
            headers={"Idempotency-Key": "canonical:mixed:update:123"},
        )
        replay = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json=request,
            headers={"Idempotency-Key": "canonical:mixed:update:123"},
        )

    assert first.status_code == 202
    assert replay.json() == first.json()
    accepted = first.json()
    update = store.repository(SiteUpdate).require(project_id, accepted["site_update_id"])
    run = store.repository(AgentRun).require(project_id, accepted["agent_run_id"])
    attachment = store.repository(Attachment).require(project_id, "att_progress123")
    task = store.repository(Task).require(project_id, "tsk_blockwork123")
    material = store.repository(Material).require(project_id, "mat_cement123")
    issues = store.repository(Issue).list(project_id)
    requests = store.repository(MaterialRequest).list(project_id)
    approvals = store.repository(Approval).list(project_id)
    reports = store.repository(DailyReport).list(project_id)
    activities = store.repository(ActivityEvent).list(project_id)

    assert interpreter.calls == [f"{update_text} {transcript}"]
    assert publisher.published_event_ids == [accepted["event_id"]]
    assert update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
    assert run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert run.step == "approval_required"
    assert attachment.site_update_id == update.id
    assert task.status is TaskStatus.COMPLETED
    assert material.available_quantity == Decimal("10")
    assert {(issue.type, tuple(issue.task_ids)) for issue in issues} == {
        (IssueType.BLOCKER, ("tsk_electrical123",)),
        (IssueType.DELAY_RISK, ("tsk_plastering123",)),
    }
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("30")
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert requests[0].approval_id == approvals[0].id
    assert len(approvals) == 1
    assert approvals[0].status is ApprovalStatus.PENDING
    assert len(reports) == 1
    assert reports[0].source_update_ids == [update.id]
    assert len(reports[0].completed_work) == 1
    assert len(reports[0].active_blockers) == 2
    assert len(reports[0].material_risks) == 1
    assert len(reports[0].next_focus) == 1
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


def test_site_update_rejects_unverified_photo_before_persisting_intake() -> None:
    project_id = "prj_readiness123"
    store = InMemoryRepositoryStore()
    attachment = Attachment(
        id="att_unverified123",
        project_id=project_id,
        object_path=f"projects/{project_id}/attachments/att_unverified123",
        content_type="image/jpeg",
        byte_size=512,
        sha256="b" * 64,
        upload_status=AttachmentUploadStatus.INITIATED,
    )
    store.repository(Attachment).create(attachment)
    publisher = WorkerPublisher(store)

    with pytest.raises(SiteUpdateAttachmentError, match="must be verified"):
        SiteUpdateIntakeService(store, publisher).submit(
            access_provider(object(), project_id, ProjectPermission.OPERATE),
            idempotency_key="unverified:photo:123",
            raw_text="Progress photo attached.",
            attachment_ids=[attachment.id],
        )

    assert publisher.published_event_ids == []
    assert store.repository(SiteUpdate).list(project_id) == ()
    assert store.repository(Attachment).require(project_id, attachment.id).site_update_id is None
    assert store.repository(ActivityEvent).list(project_id) == ()
