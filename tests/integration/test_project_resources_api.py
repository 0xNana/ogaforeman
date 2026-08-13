from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.errors import install_error_handlers, install_request_id_middleware
from app.api.v1.router import api_router
from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import (
    ActorType,
    AttachmentUploadStatus,
    ApprovalActionType,
    ApprovalStatus,
    MemberRole,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MaterialRequestStatus,
    ProjectStatus,
    ReportStatus,
    Severity,
    TaskSource,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    Project,
    ReportFact,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.materials import MaterialQuantityCommand, MaterialService


PROJECT_ID = "prj_snapshot123"
ACTOR_ID = "usr_manager123"
NOW = datetime(2026, 8, 8, 9, 45, tzinfo=UTC)


class ProjectServiceStub:
    def __init__(self, project: Project) -> None:
        self.project = project

    def require(self, access: ProjectAccessContext) -> Project:
        assert access.project_id == self.project.id
        return self.project


class ApiRuntimeStub:
    def __init__(self, project: Project, store: InMemoryRepositoryStore) -> None:
        self.projects = ProjectServiceStub(project)
        self.store = store
        self.actor = AuthenticatedUser(user_id=ACTOR_ID, subject="firebase-manager")

    def authenticate(self, request: Request) -> AuthenticatedUser:
        del request
        return self.actor

    def project_access(
        self,
        request: Request,
        project_id: str,
        permission: ProjectPermission = ProjectPermission.READ,
    ) -> ProjectAccessContext:
        del request
        assert project_id == PROJECT_ID
        return ProjectAccessContext(actor=self.actor, project_id=project_id, role=MemberRole.ADMIN)


def make_app(store: InMemoryRepositoryStore) -> FastAPI:
    project = Project(
        id=PROJECT_ID,
        name="Ridge House",
        location="East Legon, Accra",
        timezone="Africa/Accra",
        status=ProjectStatus.ACTIVE,
        created_by=ACTOR_ID,
        created_at=NOW,
        updated_at=NOW,
    )
    runtime = ApiRuntimeStub(project, store)
    app = FastAPI()
    app.state.auth_runtime = runtime
    app.state.project_access_provider = runtime.project_access
    install_request_id_middleware(app)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_new_project_snapshot_includes_persisted_creation_activity() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ActivityEvent).create(
        ActivityEvent(
            id="act_projectcreated123",
            project_id=PROJECT_ID,
            actor_type=ActorType.USER,
            actor_id=ACTOR_ID,
            action="project.created",
            entity_type="project",
            entity_id=PROJECT_ID,
            summary="Created project Ridge House.",
            created_at=NOW,
        )
    )

    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}/snapshot")

    assert response.status_code == 200
    assert response.json() == {
        "project": {
            "id": PROJECT_ID,
            "name": "Ridge House",
            "location": "East Legon, Accra",
            "status": "ACTIVE",
            "timezone": "Africa/Accra",
        },
        "viewerId": ACTOR_ID,
        "tasks": [],
        "issues": [],
        "materials": [],
        "materialRequests": [],
        "approvals": [],
        "dailyLogs": [],
        "photos": [],
        "documents": [],
        "activities": [
            {
                "id": "act_projectcreated123",
                "kind": "update",
                "title": "Created project Ridge House.",
                "description": "Created project Ridge House.",
                "date": "09:45",
                "dateLabel": "Saturday, 8 August 2026",
                "occurredAt": "2026-08-08T09:45:00+00:00",
                "user": ACTOR_ID,
                "actorType": "user",
                "action": "project.created",
                "entityType": "project",
                "entityId": PROJECT_ID,
                "needsAction": False,
                "actionLabel": None,
            }
        ],
        "report": {
            "date": "No report yet",
            "completed": [],
            "inProgress": [],
            "blocked": [],
            "materials": [],
            "tomorrow": [],
            "risks": [],
            "photos": [],
        },
    }


@pytest.mark.asyncio
async def test_admin_can_create_canonical_resources_before_site_updates() -> None:
    store = InMemoryRepositoryStore()
    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/tasks",
            json={
                "title": "First-floor blockwork",
                "planned_start": NOW.isoformat(),
                "planned_end": NOW.isoformat(),
                "is_milestone": True,
            },
            headers={"Idempotency-Key": "setup:task:blockwork"},
        )
        task_replay = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/tasks",
            json={
                "title": "First-floor blockwork",
                "planned_start": NOW.isoformat(),
                "planned_end": NOW.isoformat(),
                "is_milestone": True,
            },
            headers={"Idempotency-Key": "setup:task:blockwork"},
        )
        material = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/materials",
            json={
                "name": "Cement",
                "unit": "bags",
                "available_quantity": 0,
                "minimum_required_quantity": 10,
                "upcoming_requirement_quantity": 40,
            },
            headers={"Idempotency-Key": "setup:material:cement"},
        )
        material_id = material.json()["id"]
        access = ProjectAccessContext(
            actor=AuthenticatedUser(user_id=ACTOR_ID, subject="firebase-manager"),
            project_id=PROJECT_ID,
            role=MemberRole.ADMIN,
        )
        MaterialService(store).update_quantity(
            access,
            MaterialQuantityCommand(
                project_id=PROJECT_ID,
                material_id_or_alias=material_id,
                quantity_delta=Decimal("5"),
                unit="bags",
                expected_version=0,
                reason="Opening delivery received.",
            ),
            MutationContext(
                project_id=PROJECT_ID,
                actor_type=ActorType.USER,
                actor_id=ACTOR_ID,
                idempotency_key="setup:material:cement:stock",
            ),
        )
        material_replay = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/materials",
            json={
                "name": "Cement",
                "unit": "bags",
                "available_quantity": 0,
                "minimum_required_quantity": 10,
                "upcoming_requirement_quantity": 40,
            },
            headers={"Idempotency-Key": "setup:material:cement"},
        )
        snapshot = await client.get(f"/api/v1/projects/{PROJECT_ID}/snapshot")

    assert task.status_code == 201
    assert task_replay.status_code == 201
    assert task_replay.json() == task.json()
    assert task.json()["isMilestone"] is True
    assert material.status_code == 201
    assert material_replay.status_code == 201
    assert material_replay.json()["id"] == material.json()["id"]
    assert material_replay.json()["quantity"] == 5
    assert snapshot.status_code == 200
    assert snapshot.json()["tasks"][0]["title"] == "First-floor blockwork"
    assert snapshot.json()["materials"][0]["name"] == "Cement"
    assert {activity.action for activity in store.repository(ActivityEvent).list(PROJECT_ID)} == {
        "task.created",
        "material.created",
        "material.quantity_updated",
    }


@pytest.mark.asyncio
async def test_snapshot_projects_persisted_resources_and_latest_report() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id=PROJECT_ID,
            title="First-floor blockwork",
            status=TaskStatus.COMPLETED,
            completion_percent=Decimal("100"),
            assigned_to="usr_foreman123",
            actual_completion=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_followup123",
            project_id=PROJECT_ID,
            title="Follow up: Electrical rough-in",
            description="The assigned subcontractor was absent today.",
            status=TaskStatus.PLANNED,
            assigned_to="usr_electrician123",
            planned_start=NOW,
            planned_end=NOW,
            source=TaskSource.SITE_UPDATE,
            source_refs=["sup_update123", "iss_blocker123", "tsk_electrical123"],
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("10"),
            minimum_required_quantity=Decimal("20"),
            upcoming_requirement_quantity=Decimal("40"),
            updated_at=NOW,
        )
    )
    store.repository(Issue).create(
        Issue(
            id="iss_electrical123",
            project_id=PROJECT_ID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrician absent; ceiling work cannot start.",
            task_ids=["tsk_followup123"],
            evidence_refs=["sup_update123"],
            status=IssueStatus.OPEN,
            detected_by=IssueDetectedBy.SITE_UPDATE,
            owner_id="usr_electrician123",
            due_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id=PROJECT_ID,
            material_id="mat_cement123",
            quantity=Decimal("30"),
            unit="bags",
            needed_by=NOW,
            reason="Cement is needed for plastering.",
            source_event_id="evt_cement123",
            status=MaterialRequestStatus.AWAITING_APPROVAL,
            approval_id="apr_cement123",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Approval).create(
        Approval(
            id="apr_cement123",
            project_id=PROJECT_ID,
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_name": "Cement", "quantity": "30", "unit": "bags"},
            reason="Cement is needed for plastering.",
            evidence_refs=["su_update123"],
            requested_by="system",
            requested_at=NOW,
        )
    )
    store.repository(DailyReport).create(
        DailyReport(
            id="rpt_daily123",
            project_id=PROJECT_ID,
            report_date=date(2026, 8, 8),
            summary="Blockwork completed; cement is low.",
            completed_work=[
                ReportFact(summary="First-floor blockwork", source_refs=["su_update123"])
            ],
            material_risks=[
                ReportFact(summary="Cement stock is low", source_refs=["su_update123"])
            ],
            status=ReportStatus.PUBLISHED,
            created_at=NOW,
            updated_at=NOW,
        )
    )

    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}/snapshot")

    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["tasks"][0] == {
        "id": "tsk_blockwork123",
        "title": "First-floor blockwork",
        "status": "COMPLETED",
        "assignee": "usr_foreman123",
        "location": None,
        "trade": None,
        "startLabel": "Not set",
        "startDate": None,
        "finishDate": "2026-08-08",
        "durationDays": None,
        "isMilestone": False,
        "downstreamIds": [],
        "atRisk": False,
        "dueLabel": "Completed 8 Aug",
        "progress": 100,
        "dependencyIds": [],
        "blocking": None,
        "note": "100% complete.",
        "needsAttention": False,
        "sourceRefs": [],
    }
    assert snapshot["tasks"][1]["title"] == "Follow up: Electrical rough-in"
    assert snapshot["tasks"][1]["needsAttention"] is True
    assert snapshot["tasks"][1]["startDate"] == "2026-08-08"
    assert snapshot["tasks"][1]["finishDate"] == "2026-08-08"
    assert snapshot["tasks"][1]["durationDays"] == 1
    assert snapshot["tasks"][1]["isMilestone"] is False
    assert snapshot["tasks"][1]["sourceRefs"] == [
        "sup_update123",
        "iss_blocker123",
        "tsk_electrical123",
    ]
    assert snapshot["materials"][0]["status"] == "REQUESTED"
    assert snapshot["materials"][0]["quantity"] == 10
    assert snapshot["issues"][0] == {
        "id": "iss_electrical123",
        "description": "Electrician absent; ceiling work cannot start.",
        "type": "BLOCKER",
        "severity": "HIGH",
        "status": "OPEN",
        "owner": "usr_electrician123",
        "dueLabel": "8 Aug",
        "taskIds": ["tsk_followup123"],
        "evidenceRefs": ["sup_update123"],
        "location": None,
    }
    assert snapshot["materialRequests"][0] == {
        "id": "mrq_cement123",
        "materialId": "mat_cement123",
        "materialName": "Cement",
        "quantity": 30,
        "unit": "bags",
        "reason": "Cement is needed for plastering.",
        "neededBy": "8 Aug",
        "status": "AWAITING_APPROVAL",
        "approvalId": "apr_cement123",
    }
    assert snapshot["approvals"][0]["version"] == 0
    assert snapshot["approvals"][0]["quantity"] == "30 bags"
    assert snapshot["report"]["completed"] == ["First-floor blockwork"]
    assert snapshot["report"]["materials"] == ["Cement stock is low"]
    assert snapshot["dailyLogs"] == [
        {
            "id": "rpt_daily123",
            "date": "Saturday, 8 August",
            "dateIso": "2026-08-08",
            "summary": "Blockwork completed; cement is low.",
            "crew": None,
            "weather": None,
            "completed": ["First-floor blockwork"],
            "inProgress": [],
            "blocked": [],
            "materials": ["Cement stock is low"],
            "deliveries": [],
            "inspections": [],
            "photos": [],
            "tomorrow": [],
            "risks": ["Cement stock is low"],
            "sourceUpdateCount": 0,
            "status": "PUBLISHED",
            "version": 0,
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_projects_verified_media_with_relationships() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Attachment).create(
        Attachment(
            id="att_progress123",
            project_id=PROJECT_ID,
            site_update_id="sup_progress123",
            object_path=f"projects/{PROJECT_ID}/attachments/att_progress123",
            original_name="north-elevation.jpg",
            content_type="image/jpeg",
            byte_size=2048,
            sha256="a" * 64,
            upload_status=AttachmentUploadStatus.VERIFIED,
            uploaded_by=ACTOR_ID,
            created_at=NOW,
        )
    )
    store.repository(Attachment).create(
        Attachment(
            id="att_method123",
            project_id=PROJECT_ID,
            object_path=f"projects/{PROJECT_ID}/attachments/att_method123",
            original_name="blockwork-method.pdf",
            content_type="application/pdf",
            byte_size=4096,
            sha256="b" * 64,
            upload_status=AttachmentUploadStatus.VERIFIED,
            uploaded_by=ACTOR_ID,
            created_at=NOW,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id=PROJECT_ID,
            title="First-floor blockwork",
            source=TaskSource.SITE_UPDATE,
            source_refs=["sup_progress123"],
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(Issue).create(
        Issue(
            id="iss_quality123",
            project_id=PROJECT_ID,
            type=IssueType.QUALITY,
            severity=Severity.MEDIUM,
            description="Check north elevation joints.",
            evidence_refs=["sup_progress123"],
            detected_by=IssueDetectedBy.SITE_UPDATE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    store.repository(DailyReport).create(
        DailyReport(
            id="rpt_media123",
            project_id=PROJECT_ID,
            report_date=date(2026, 8, 8),
            summary="North elevation progress recorded.",
            source_update_ids=["sup_progress123"],
            status=ReportStatus.PUBLISHED,
            created_at=NOW,
            updated_at=NOW,
        )
    )

    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["photos"] == [
        {
            "id": "att_progress123",
            "name": "north-elevation.jpg",
            "contentType": "image/jpeg",
            "date": "8 Aug 2026, 09:45",
            "dateIso": "2026-08-08T09:45:00+00:00",
            "uploadedBy": ACTOR_ID,
            "location": None,
            "siteUpdateId": "sup_progress123",
            "taskIds": ["tsk_blockwork123"],
            "issueIds": ["iss_quality123"],
            "dailyLogIds": ["rpt_media123"],
        }
    ]
    assert payload["documents"] == [
        {
            "id": "att_method123",
            "name": "blockwork-method.pdf",
            "type": "PDF",
            "revision": None,
            "uploadedBy": ACTOR_ID,
            "updated": "8 Aug 2026",
            "siteUpdateId": None,
            "linkedRecords": [],
        }
    ]


@pytest.mark.asyncio
async def test_admin_edits_daily_log_metadata_with_activity_and_idempotency() -> None:
    store = InMemoryRepositoryStore()
    store.repository(DailyReport).create(
        DailyReport(
            id="rpt_edit123",
            project_id=PROJECT_ID,
            report_date=date(2026, 8, 8),
            summary="Initial summary.",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)
    headers = {"Idempotency-Key": "daily-log:edit:123"}
    payload = {
        "summary": "Client-ready summary.",
        "crew_summary": "12 workers",
        "weather_summary": "Dry",
        "expected_version": 0,
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        edited = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/daily-logs/rpt_edit123/edit",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/daily-logs/rpt_edit123/edit",
            json=payload,
            headers=headers,
        )

    assert edited.status_code == 200
    assert replay.json() == edited.json()
    assert edited.json()["crew"] == "12 workers"
    assert edited.json()["weather"] == "Dry"
    assert edited.json()["version"] == 1
    assert [event.action for event in store.repository(ActivityEvent).list(PROJECT_ID)] == [
        "daily_log.edited"
    ]


@pytest.mark.asyncio
async def test_approval_decision_updates_projection_and_rejects_stale_version() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Approval).create(
        Approval(
            id="apr_decision123",
            project_id=PROJECT_ID,
            action_type=ApprovalActionType.HIGH_IMPACT_CHANGE,
            proposed_action={"title": "Change access sequence"},
            reason="The access sequence affects tomorrow's work.",
            requested_by="system",
            requested_at=NOW,
        )
    )
    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approved = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/approvals/apr_decision123/decision",
            json={"decision": "approved", "expected_version": 0},
            headers={"Idempotency-Key": "approval:approve:123"},
        )
        stale = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/approvals/apr_decision123/decision",
            json={"decision": "rejected", "expected_version": 0},
            headers={"Idempotency-Key": "approval:reject:stale:123"},
        )

    assert approved.status_code == 200
    assert approved.json()["status"] == ApprovalStatus.APPROVED.value.upper()
    assert approved.json()["version"] == 1
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT_VERSION_MISMATCH"
