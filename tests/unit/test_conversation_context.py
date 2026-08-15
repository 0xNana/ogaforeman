from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectForbiddenError
from app.domain.conversation import ContextDomain
from app.domain.enums import (
    ActorType,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MemberRole,
    MemberStatus,
    ProjectStatus,
    Severity,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    DailyReport,
    Issue,
    Material,
    Project,
    ProjectMember,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_context import (
    ProjectContextService,
    plan_context_query,
)


NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)
PROJECT_ID = "prj_context123"


class ProjectReader:
    def __init__(self, project: Project) -> None:
        self.project = project

    def require(self, access: ProjectAccessContext) -> Project:
        return self.project


def access(project_id: str = PROJECT_ID) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_viewer123", subject="firebase-viewer"),
        project_id=project_id,
        role=MemberRole.VIEWER,
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "what's up?",
            {
                ContextDomain.PROJECT,
                ContextDomain.TASKS,
                ContextDomain.ISSUES,
                ContextDomain.MATERIALS,
                ContextDomain.APPROVALS,
                ContextDomain.SCHEDULE,
            },
        ),
        (
            "what happened today?",
            {ContextDomain.TASKS, ContextDomain.DAILY_LOGS, ContextDomain.RECENT_ACTIVITY},
        ),
        ("what's blocking us?", {ContextDomain.ISSUES, ContextDomain.TASKS}),
        ("what's late?", {ContextDomain.SCHEDULE, ContextDomain.TASKS}),
        ("what materials are low?", {ContextDomain.MATERIALS, ContextDomain.MATERIAL_REQUESTS}),
        ("what needs approval?", {ContextDomain.APPROVALS, ContextDomain.MATERIAL_REQUESTS}),
        ("what happens tomorrow?", {ContextDomain.SCHEDULE, ContextDomain.TASKS}),
        (
            "who owns electrical?",
            {ContextDomain.TASKS, ContextDomain.ISSUES, ContextDomain.PROJECT_MEMBERS},
        ),
        (
            "why is plastering at risk?",
            {
                ContextDomain.TASKS,
                ContextDomain.ISSUES,
                ContextDomain.SCHEDULE,
                ContextDomain.DAILY_LOGS,
            },
        ),
    ],
)
def test_query_planner_selects_only_relevant_domains(
    message: str,
    expected: set[ContextDomain],
) -> None:
    query = plan_context_query(message)

    assert set(query.domains) == expected


@pytest.mark.parametrize("message", ["how about site clearance", "what about electrical"])
def test_query_planner_searches_entity_follow_up(message: str) -> None:
    query = plan_context_query(message)

    assert ContextDomain.TASKS in query.domains
    assert query.search_terms
    assert "site" in query.search_terms or "electrical" in query.search_terms


def test_context_is_project_scoped_typed_bounded_and_derived_from_current_state() -> None:
    store = InMemoryRepositoryStore()
    project = Project(
        id=PROJECT_ID,
        name="Airport Residence",
        location="Accra",
        timezone="Africa/Accra",
        status=ProjectStatus.ACTIVE,
        created_by="usr_admin123",
    )
    task = Task(
        id="tsk_electrical123",
        project_id=PROJECT_ID,
        title="Electrical rough-in",
        status=TaskStatus.BLOCKED,
        assigned_to="usr_kofi123",
        planned_start=NOW + timedelta(hours=12),
        planned_end=NOW + timedelta(days=1),
    )
    store.repository(Task).create(task)
    store.repository(Task).create(
        Task(
            id="tsk_otherproject123",
            project_id="prj_other123",
            title="Secret other-project task",
            status=TaskStatus.BLOCKED,
        )
    )
    store.repository(Issue).create(
        Issue(
            id="iss_electrical123",
            project_id=PROJECT_ID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrician did not arrive.",
            task_ids=[task.id],
            status=IssueStatus.OPEN,
            detected_by=IssueDetectedBy.SITE_UPDATE,
            owner_id="usr_kofi123",
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
            minimum_required_quantity=Decimal("40"),
        )
    )
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=PROJECT_ID,
            user_id="usr_kofi123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )

    service = ProjectContextService(
        store,
        ProjectReader(project),
        member_names=lambda project_id: {"usr_kofi123": "Kofi Mensah"},
    )
    snapshot = service.retrieve(access(), plan_context_query("who owns electrical?"), now=NOW)

    assert snapshot.project is None
    assert [item.title for item in snapshot.tasks] == ["Electrical rough-in"]
    assert snapshot.tasks[0].assignee_name == "Kofi Mensah"
    assert snapshot.issues[0].owner_name == "Kofi Mensah"
    assert snapshot.members[0].display_name == "Kofi Mensah"
    assert snapshot.materials == ()
    assert "Secret other-project task" not in snapshot.model_dump_json()
    assert len(store.repository(ActivityEvent).list(PROJECT_ID)) == 0


def test_context_filters_operational_views_without_mutating_repositories() -> None:
    store = InMemoryRepositoryStore()
    project = Project(
        id=PROJECT_ID,
        name="Airport Residence",
        location="Accra",
        timezone="Africa/Accra",
        status=ProjectStatus.ACTIVE,
        created_by="usr_admin123",
    )
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("10"),
            minimum_required_quantity=Decimal("40"),
        )
    )
    store.repository(Material).create(
        Material(
            id="mat_sand123",
            project_id=PROJECT_ID,
            name="Sand",
            normalized_name="sand",
            unit="tonnes",
            available_quantity=Decimal("50"),
            minimum_required_quantity=Decimal("10"),
        )
    )
    store.repository(DailyReport).create(
        DailyReport(
            id="rpt_today123",
            project_id=PROJECT_ID,
            report_date=date(2026, 8, 13),
            summary="Blockwork was completed today.",
        )
    )
    store.repository(ActivityEvent).create(
        ActivityEvent(
            id="act_today123",
            project_id=PROJECT_ID,
            actor_type=ActorType.SYSTEM,
            action="task.completed",
            entity_type="task",
            entity_id="tsk_blockwork123",
            summary="Blockwork completed.",
            created_at=NOW - timedelta(hours=1),
        )
    )

    service = ProjectContextService(store, ProjectReader(project), max_items_per_domain=5)
    materials = service.retrieve(access(), plan_context_query("what materials are low?"), now=NOW)
    today = service.retrieve(access(), plan_context_query("what happened today?"), now=NOW)

    assert [item.name for item in materials.materials] == ["Cement"]
    assert today.daily_logs[0].summary == "Blockwork was completed today."
    assert today.recent_activity[0].summary == "Blockwork completed."
    assert len(store.repository(Material).list(PROJECT_ID)) == 2


def test_context_rejects_a_project_reader_that_returns_another_project() -> None:
    other = Project(
        id="prj_other123",
        name="Other",
        location="Kumasi",
        timezone="Africa/Accra",
        created_by="usr_other123",
    )

    with pytest.raises(ProjectForbiddenError):
        ProjectContextService(InMemoryRepositoryStore(), ProjectReader(other)).retrieve(
            access(), plan_context_query("what's up?"), now=NOW
        )
