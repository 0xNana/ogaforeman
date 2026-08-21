from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.interpreter import FakeSiteInterpreter
from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import (
    ActorType,
    IssueType,
    MemberRole,
    MemberStatus,
    Severity,
    SiteUpdateInputType,
    TaskStatus,
)
from app.domain.facts import ExtractedFactSet, IssueFact, MaterialQuantityFact, NextFocusFact
from app.domain.import_records import ProjectImportRecord
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import (
    ActivityEvent,
    Approval,
    Issue,
    Material,
    MaterialRequest,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.domain.project_import import DraftTaskStatus, ProjectImportDraft, ProjectImportStatus
from app.repositories.context import ContextRepository
from app.repositories.memory import InMemoryRepositoryStore
from app.services.context import ContextService
from app.services.issues import IssueService
from app.services.material_requests import MaterialRequestService
from app.services.materials import CreateMaterialCommand, MaterialService
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


def _import_plan(
    store: InMemoryRepositoryStore,
    *,
    plastering_requirement: Decimal = Decimal("100"),
    unrelated_requirement: Decimal = Decimal("200"),
    include_dependency: bool = True,
) -> ProjectImportDraft:
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
        dependencies=(
            [
                {
                    "predecessor_temp_id": "tmp_task_plastering",
                    "successor_temp_id": "tmp_task_external_works",
                }
            ]
            if include_dependency
            else []
        ),
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
                "required_quantity": plastering_requirement,
                "unit": "bags",
            },
            {
                "task_temp_id": "tmp_task_external_works",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": unrelated_requirement,
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
    *,
    raw_text: str = UPDATE_TEXT,
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
        raw_text=raw_text,
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


def _site_update_service(
    store: InMemoryRepositoryStore,
    access: ProjectAccessContext,
    interpreter: FakeSiteInterpreter,
) -> SiteUpdateService:
    return SiteUpdateService(
        interpreter=interpreter,
        context_service=ContextService(ContextRepository(store)),
        task_tools=TaskTools(TaskService(store), access),
        material_tools=MaterialTools(MaterialService(store), access),
        issue_service=IssueService(store),
        material_request_service=MaterialRequestService(store),
        report_service=ReportService(store),
        workflow_audit=WorkflowAuditService(store),
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
@pytest.mark.parametrize(
    ("plastering_requirement", "unrelated_requirement", "expected_shortage"),
    [
        (Decimal("100"), Decimal("200"), Decimal("90")),
        (Decimal("80"), Decimal("900"), Decimal("70")),
    ],
)
async def test_imported_focus_task_requirement_drives_operational_shortage(
    plastering_requirement: Decimal,
    unrelated_requirement: Decimal,
    expected_shortage: Decimal,
) -> None:
    store = InMemoryRepositoryStore()
    _import_plan(
        store,
        plastering_requirement=plastering_requirement,
        unrelated_requirement=unrelated_requirement,
    )
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

    result = await _site_update_service(store, access, interpreter).process_update(
        access=access,
        site_update=update,
        run_id="run_phase18update",
        trace_id=EVENT_ID,
        source_event_id=EVENT_ID,
    )

    requests = store.repository(MaterialRequest).list(PROJECT_ID)
    assert len(requests) == 1
    assert requests[0].quantity == expected_shortage
    plastering = next(
        task for task in store.repository(Task).list(PROJECT_ID) if task.title == "Plastering"
    )
    approval = store.repository(Approval).list(PROJECT_ID)[0]
    assert approval.proposed_action["affected_task_ids"] == [plastering.id]
    assert result.has_pending_approvals
    assert result.pending_actions == (
        f"Manager approval required for {expected_shortage} bags of Cement.",
    )


@pytest.mark.asyncio
async def test_material_stock_update_without_focus_context_creates_no_shortage_request() -> None:
    store = InMemoryRepositoryStore()
    _import_plan(store)
    access, update = _seed_operational_update(store)
    interpreter = FakeSiteInterpreter(
        responses={
            UPDATE_TEXT: ExtractedFactSet(
                materials=[
                    MaterialQuantityFact(
                        material_name="Cement",
                        quantity=8,
                        unit="bags",
                        evidence="We have eight bags of cement left.",
                        confidence="high",
                    )
                ]
            )
        }
    )

    result = await _site_update_service(store, access, interpreter).process_update(
        access=access,
        site_update=update,
        run_id="run_phase18no_focus",
        trace_id="evt_phase18no_focus",
        source_event_id="evt_phase18no_focus",
    )

    cement = next(
        material
        for material in store.repository(Material).list(PROJECT_ID)
        if material.name == "Cement"
    )
    assert cement.available_quantity == Decimal("8")
    assert store.repository(MaterialRequest).list(PROJECT_ID) == ()
    assert result.materials_updated == 1
    assert result.has_pending_approvals is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("include_dependency", "expect_downstream_risk"),
    [(True, True), (False, False)],
)
async def test_blocker_impact_uses_only_imported_dependency_records(
    include_dependency: bool,
    expect_downstream_risk: bool,
) -> None:
    blocker_text = "Plastering is blocked because the crew did not arrive."
    store = InMemoryRepositoryStore()
    _import_plan(store, include_dependency=include_dependency)
    access, update = _seed_operational_update(store, raw_text=blocker_text)
    tasks = store.repository(Task).list(PROJECT_ID)
    plastering = next(task for task in tasks if task.title == "Plastering")
    external_works = next(task for task in tasks if task.title == "External works")
    assert external_works.dependency_ids == ([plastering.id] if include_dependency else [])

    interpreter = FakeSiteInterpreter(
        responses={
            blocker_text: ExtractedFactSet(
                issues=[
                    IssueFact(
                        issue_type=IssueType.BLOCKER,
                        task_name="Plastering",
                        description="The plastering crew did not arrive.",
                        severity=Severity.HIGH,
                        evidence=blocker_text,
                        confidence="high",
                    )
                ]
            )
        }
    )

    case_id = "edge" if include_dependency else "noedge"
    await _site_update_service(store, access, interpreter).process_update(
        access=access,
        site_update=update,
        run_id=f"run_phase18dependency_{case_id}",
        trace_id=f"evt_phase18dependency_{case_id}",
        source_event_id=f"evt_phase18dependency_{case_id}",
    )

    delay_risks = [
        issue
        for issue in store.repository(Issue).list(PROJECT_ID)
        if issue.type is IssueType.DELAY_RISK
    ]
    if expect_downstream_risk:
        assert [issue.task_ids for issue in delay_risks] == [[external_works.id]]
    else:
        assert delay_risks == []


@pytest.mark.asyncio
async def test_operational_material_creation_coexists_with_imported_state_and_replays_once() -> (
    None
):
    store = InMemoryRepositoryStore()
    _import_plan(store)
    access, _update = _seed_operational_update(store)
    tools = MaterialTools(MaterialService(store), access)
    context = MutationContext(
        project_id=PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id=FOREMAN_ID,
        source_event_id="evt_phase18wire",
        agent_run_id="run_phase18wire",
        idempotency_key="material:auto-create:building-wire",
        occurred_at=NOW,
    )
    command = CreateMaterialCommand(
        project_id=PROJECT_ID,
        name="Building Wire",
        unit="piece",
        available_quantity=Decimal("60"),
    )

    first = tools.create_material(command, context, permission=ProjectPermission.OPERATE)
    replay = tools.create_material(command, context, permission=ProjectPermission.OPERATE)

    wires = [
        material
        for material in store.repository(Material).list(PROJECT_ID)
        if material.name == "Building Wire"
    ]
    assert len(wires) == 1
    assert wires[0].unit == "pieces"
    assert wires[0].available_quantity == Decimal("60")
    wire_ledger = [
        entry
        for entry in store.repository(MaterialLedgerEntry).list(PROJECT_ID)
        if entry.material_id == wires[0].id
    ]
    assert len(wire_ledger) == 1
    assert wire_ledger[0].quantity_delta == Decimal("60")
    wire_activities = [
        activity
        for activity in store.repository(ActivityEvent).list(PROJECT_ID)
        if activity.action == "material.created" and activity.entity_id == wires[0].id
    ]
    assert len(wire_activities) == 1
    assert len(store.repository(ProjectImportRecord).list(PROJECT_ID)) == 1
    assert first.duplicate is False
    assert replay.duplicate is True
    assert replay.material.id == wires[0].id
