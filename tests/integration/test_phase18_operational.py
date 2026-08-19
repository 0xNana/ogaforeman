from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.interpreter import FakeSiteInterpreter
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    MemberRole,
    MemberStatus,
    SiteUpdateInputType,
    TaskStatus,
)
from app.domain.facts import ExtractedFactSet, MaterialQuantityFact, NextFocusFact
from app.domain.import_records import ProjectImportRecord
from app.domain.models import MaterialRequest, ProjectMember, SiteUpdate, Task
from app.domain.project_import import DraftTaskStatus, ProjectImportDraft, ProjectImportStatus
from app.repositories.context import ContextRepository
from app.repositories.memory import InMemoryRepositoryStore
from app.services.context import ContextService
from app.services.issues import IssueService
from app.services.material_requests import MaterialRequestService
from app.services.materials import MaterialService
from app.services.project_import import ProjectImportService
from app.services.project_sources import ProjectSourceService
from app.services.reports import ReportService
from app.services.site_updates import SiteUpdateService
from app.services.tasks import TaskService
from app.services.workflow_audit import WorkflowAuditService
from app.tools.materials import MaterialTools
from app.tools.tasks import TaskTools


NOW = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
PROJECT_ID = "prj_phase18site"
ADMIN_ID = "usr_phase18admin"
FOREMAN_ID = "usr_phase18foreman"
SOURCE_ID = "src_phase18plan"
IMPORT_ID = "imp_phase18plan"
UPDATE_ID = "sup_phase18update"
EVENT_ID = "evt_phase18update"
UPDATE_TEXT = "Plastering is next. We have ten bags of cement left."


def _import_plan(store: InMemoryRepositoryStore) -> ProjectImportDraft:
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=ADMIN_ID, subject="phase18-admin"),
        project_id=PROJECT_ID,
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id=SOURCE_ID,
        name="ridge-house.md",
        text=(
            "Plastering requires 100 bags of cement. "
            "External works requires another 200 bags. Ten bags are on hand."
        ),
    )
    draft = ProjectImportDraft(
        id=IMPORT_ID,
        project_id=PROJECT_ID,
        source_id=SOURCE_ID,
        status=ProjectImportStatus.CONFIRMED,
        confirmed_at=NOW,
        project={"name": "Ridge House"},
        tasks=[
            {
                "temp_id": "tmp_task_plastering",
                "name": "Plastering",
                "planned_start": date(2026, 8, 20),
                "planned_finish": date(2026, 8, 25),
                "initial_status": DraftTaskStatus.PLANNED,
            },
            {
                "temp_id": "tmp_task_external_works",
                "name": "External works",
                "planned_start": date(2026, 9, 1),
                "planned_finish": date(2026, 9, 10),
                "initial_status": DraftTaskStatus.PLANNED,
            },
        ],
        materials=[
            {
                "temp_id": "tmp_material_cement",
                "name": "Cement",
                "canonical_unit": "bags",
                "initial_on_hand_quantity": Decimal("10"),
            }
        ],
        material_requirements=[
            {
                "task_temp_id": "tmp_task_plastering",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("100"),
                "unit": "bags",
            },
            {
                "task_temp_id": "tmp_task_external_works",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("200"),
                "unit": "bags",
            },
        ],
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="phase18-confirm-plan",
    )
    return draft


def _seed_operational_update(
    store: InMemoryRepositoryStore,
) -> tuple[ProjectAccessContext, SiteUpdate]:
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=PROJECT_ID,
            user_id=FOREMAN_ID,
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    update = SiteUpdate(
        id=UPDATE_ID,
        project_id=PROJECT_ID,
        submitted_by=FOREMAN_ID,
        input_type=SiteUpdateInputType.TEXT,
        raw_text=UPDATE_TEXT,
        client_event_id="phase18-browser-event",
        submitted_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    store.repository(SiteUpdate).create(update)
    return (
        ProjectAccessContext(
            actor=AuthenticatedUser(user_id=FOREMAN_ID, subject="phase18-foreman"),
            project_id=PROJECT_ID,
            role=MemberRole.FOREMAN,
        ),
        update,
    )


def test_import_commit_preserves_initial_completed_state() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=ADMIN_ID, subject="phase18-admin"),
        project_id=PROJECT_ID,
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id=SOURCE_ID,
        name="ridge-house.md",
        text="Excavation completed on 18 August 2026.",
    )
    draft = ProjectImportDraft(
        id=IMPORT_ID,
        project_id=PROJECT_ID,
        source_id=SOURCE_ID,
        status=ProjectImportStatus.CONFIRMED,
        confirmed_at=NOW,
        project={"name": "Ridge House"},
        tasks=[
            {
                "temp_id": "tmp_task_excavation",
                "name": "Excavation",
                "initial_status": DraftTaskStatus.COMPLETED,
                "actual_completion": date(2026, 8, 18),
            }
        ],
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="phase18-confirm-completed-state",
    )

    tasks = store.repository(Task).list(PROJECT_ID)
    assert len(tasks) == 1
    assert tasks[0].status is TaskStatus.COMPLETED
    assert tasks[0].actual_completion == datetime(2026, 8, 18, tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="PI-09 must calculate shortage from resolved focus-task requirements only",
)
async def test_imported_focus_task_requirement_drives_operational_shortage() -> None:
    store = InMemoryRepositoryStore()
    _import_plan(store)
    access, update = _seed_operational_update(store)
    interpreter = FakeSiteInterpreter(
        responses={
            UPDATE_TEXT: ExtractedFactSet(
                materials=[
                    MaterialQuantityFact(
                        material_name="Cement",
                        quantity=10,
                        unit="bags",
                        evidence="We have ten bags of cement left.",
                        confidence="high",
                    )
                ],
                next_focus=[
                    NextFocusFact(
                        task_name="Plastering",
                        description="Plastering is next.",
                        evidence="Plastering is next.",
                        confidence="high",
                    )
                ],
            )
        }
    )

    result = await SiteUpdateService(
        interpreter=interpreter,
        context_service=ContextService(ContextRepository(store)),
        task_tools=TaskTools(TaskService(store), access),
        material_tools=MaterialTools(MaterialService(store), access),
        issue_service=IssueService(store),
        material_request_service=MaterialRequestService(store),
        report_service=ReportService(store),
        workflow_audit=WorkflowAuditService(store),
    ).process_update(
        access=access,
        site_update=update,
        run_id="run_phase18update",
        trace_id=EVENT_ID,
        source_event_id=EVENT_ID,
    )

    requests = store.repository(MaterialRequest).list(PROJECT_ID)
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("90")
    assert result.has_pending_approvals
    assert result.pending_actions == ("Manager approval required for 90 bags of Cement.",)
