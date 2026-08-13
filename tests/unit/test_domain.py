from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.domain.enums import ProjectStatus, TaskPriority, TaskSource, TaskStatus
from app.domain.models import Project, Task
from app.domain.policies import (
    InvalidTransitionError,
    ensure_task_transition,
    validate_task_dependency_graph,
)


NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


def make_task(
    task_id: str,
    *,
    project_id: str = "prj_ridge",
    dependency_ids: list[str] | None = None,
) -> Task:
    return Task(
        id=task_id,
        project_id=project_id,
        title=task_id.replace("tsk_", "").replace("_", " ").title(),
        status=TaskStatus.PLANNED,
        priority=TaskPriority.MEDIUM,
        dependency_ids=dependency_ids or [],
        source=TaskSource.MANUAL,
    )


def test_project_uses_canonical_id_and_timezone_aware_timestamps() -> None:
    project = Project(
        id="prj_ridge",
        name="Ridge Project",
        location="Accra",
        timezone="Africa/Accra",
        status=ProjectStatus.ACTIVE,
        created_by="usr_admin",
    )

    assert project.created_at.tzinfo is not None
    assert project.updated_at.tzinfo is not None
    assert project.created_at.utcoffset() == UTC.utcoffset(project.created_at)


@pytest.mark.parametrize("project_id", ["ridge", "PRJ_ridge", "prj_", "prj ridge"])
def test_project_rejects_noncanonical_ids(project_id: str) -> None:
    with pytest.raises(ValidationError):
        Project(
            id=project_id,
            name="Ridge Project",
            location="Accra",
            timezone="Africa/Accra",
            created_by="usr_admin",
        )


def test_project_rejects_invalid_timezone_and_date_order() -> None:
    with pytest.raises(ValidationError, match="IANA timezone"):
        Project(
            id="prj_ridge",
            name="Ridge Project",
            location="Accra",
            timezone="Accra/Invalid",
            created_by="usr_admin",
        )

    with pytest.raises(ValidationError, match="target_end_date"):
        Project(
            id="prj_ridge",
            name="Ridge Project",
            location="Accra",
            timezone="Africa/Accra",
            start_date=date(2026, 8, 8),
            target_end_date=date(2026, 8, 7),
            created_by="usr_admin",
        )


def test_task_rejects_naive_datetimes() -> None:
    with pytest.raises(ValidationError):
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            planned_start=datetime(2026, 8, 7, 10, 0),
        )


def test_completed_task_requires_full_progress_and_completion_time() -> None:
    with pytest.raises(ValidationError, match="completion_percent"):
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            status=TaskStatus.COMPLETED,
            completion_percent=90,
            actual_completion=NOW,
        )

    with pytest.raises(ValidationError, match="actual_completion"):
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            status=TaskStatus.COMPLETED,
            completion_percent=100,
        )


def test_task_rejects_invalid_progress_dates_and_dependencies() -> None:
    with pytest.raises(ValidationError):
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            completion_percent=101,
        )

    with pytest.raises(ValidationError, match="planned_end"):
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            planned_start=NOW,
            planned_end=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
        )

    with pytest.raises(ValidationError, match="depend on itself"):
        make_task("tsk_blockwork", dependency_ids=["tsk_blockwork"])

    with pytest.raises(ValidationError, match="duplicate"):
        make_task("tsk_blockwork", dependency_ids=["tsk_foundation", "tsk_foundation"])


def test_dependency_graph_rejects_missing_cross_project_and_cyclic_dependencies() -> None:
    foundation = make_task("tsk_foundation")
    blockwork = make_task("tsk_blockwork", dependency_ids=["tsk_foundation"])

    validate_task_dependency_graph([foundation, blockwork])

    with pytest.raises(ValueError, match="missing task"):
        validate_task_dependency_graph([make_task("tsk_blockwork", dependency_ids=["tsk_unknown"])])

    with pytest.raises(ValueError, match="same project"):
        validate_task_dependency_graph([foundation, make_task("tsk_other", project_id="prj_other")])

    with pytest.raises(ValueError, match="cycle"):
        validate_task_dependency_graph(
            [
                make_task("tsk_foundation", dependency_ids=["tsk_blockwork"]),
                make_task("tsk_blockwork", dependency_ids=["tsk_foundation"]),
            ]
        )


def test_task_transition_policy_blocks_automatic_reopening() -> None:
    ensure_task_transition(TaskStatus.PLANNED, TaskStatus.IN_PROGRESS)

    with pytest.raises(InvalidTransitionError):
        ensure_task_transition(TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS)

    ensure_task_transition(
        TaskStatus.COMPLETED,
        TaskStatus.IN_PROGRESS,
        human_correction=True,
    )

    with pytest.raises(InvalidTransitionError):
        ensure_task_transition(
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            human_correction=True,
        )


def test_task_transition_policy_limits_reconciled_completion_to_planned_tasks() -> None:
    with pytest.raises(InvalidTransitionError):
        ensure_task_transition(TaskStatus.PLANNED, TaskStatus.COMPLETED)

    ensure_task_transition(
        TaskStatus.PLANNED,
        TaskStatus.COMPLETED,
        reconciled_completion=True,
    )
    ensure_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED)

    with pytest.raises(InvalidTransitionError):
        ensure_task_transition(
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            reconciled_completion=True,
        )
    with pytest.raises(InvalidTransitionError):
        ensure_task_transition(
            TaskStatus.BLOCKED,
            TaskStatus.COMPLETED,
            reconciled_completion=True,
        )
