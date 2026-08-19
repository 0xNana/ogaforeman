from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import ProjectReadinessState
from app.domain.enums import MemberRole, ProjectStatus, TaskSource, TaskStatus
from app.domain.import_records import MaterialRequirement
from app.domain.models import Material, Project, Task
from app.repositories.memory import InMemoryRepositoryStore
from app.services.project_setup import ProjectSetupService


PROJECT_ID = "prj_readiness123"


class ProjectReader:
    def __init__(self, project: Project) -> None:
        self._project = project

    def require(self, access: ProjectAccessContext) -> Project:
        assert access.project_id == self._project.id
        return self._project


def _access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="readiness-test"),
        project_id=PROJECT_ID,
        role=MemberRole.ADMIN,
    )


def _project() -> Project:
    return Project(
        id=PROJECT_ID,
        name="Ridge House",
        location="Accra",
        timezone="Africa/Accra",
        status=ProjectStatus.ACTIVE,
        created_by="usr_admin123",
    )


def test_readiness_is_operational_with_imported_plan_and_reports_setup_gaps() -> None:
    store = InMemoryRepositoryStore()
    first_task = Task(
        id="tsk_foundation123",
        project_id=PROJECT_ID,
        title="Foundation",
        status=TaskStatus.IN_PROGRESS,
        source=TaskSource.IMPORT,
        planned_start=datetime(2026, 8, 18, tzinfo=UTC),
        planned_end=datetime(2026, 8, 21, tzinfo=UTC),
    )
    store.repository(Task).create(first_task)
    store.repository(Task).create(
        Task(
            id="tsk_plastering123",
            project_id=PROJECT_ID,
            title="Plastering",
            status=TaskStatus.PLANNED,
            source=TaskSource.IMPORT,
            dependency_ids=[first_task.id],
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id=PROJECT_ID,
            title="Blockwork",
            status=TaskStatus.PLANNED,
            source=TaskSource.IMPORT,
        )
    )
    material = Material(
        id="mat_cement123",
        project_id=PROJECT_ID,
        name="Cement",
        normalized_name="cement",
        unit="bags",
        available_quantity=Decimal("10"),
    )
    store.repository(Material).create(material)
    store.repository(MaterialRequirement).create(
        MaterialRequirement(
            id="req_plastering123",
            project_id=PROJECT_ID,
            import_id="imp_readiness123",
            task_id="tsk_plastering123",
            material_id=material.id,
            required_quantity=Decimal("100"),
            unit="bags",
            required_by=date(2026, 8, 22),
        )
    )

    status = ProjectSetupService(store, ProjectReader(_project())).retrieve(_access())

    assert status.readiness_state is ProjectReadinessState.OPERATIONAL
    assert status.task_count == 3
    assert status.dependency_count == 1
    assert status.has_dependencies
    assert status.has_materials
    assert status.has_material_requirements
    assert status.material_requirement_task_count == 1
    assert status.planned_tasks_without_material_requirements == 1
    assert status.has_schedule
    assert status.has_initial_state


def test_readiness_is_empty_without_canonical_project_configuration() -> None:
    status = ProjectSetupService(InMemoryRepositoryStore(), ProjectReader(_project())).retrieve(
        _access()
    )

    assert status.readiness_state is ProjectReadinessState.EMPTY


def test_readiness_is_partially_configured_without_tasks() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Material).create(
        Material(
            id="mat_sand123",
            project_id=PROJECT_ID,
            name="Sand",
            normalized_name="sand",
            unit="tonnes",
            available_quantity=Decimal("4"),
        )
    )

    status = ProjectSetupService(store, ProjectReader(_project())).retrieve(_access())

    assert status.readiness_state is ProjectReadinessState.PARTIALLY_CONFIGURED
    assert status.has_materials
    assert not status.has_tasks
