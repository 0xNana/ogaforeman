from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.import_records import MaterialRequirement, ProjectPhase
from app.domain.models import Material, Task
from app.domain.project_import import ProjectDraft, ProjectImportDraft, TaskDraft
from app.repositories.context import ProjectContext
from app.services.project_import_diff import (
    DiffOperation,
    EntityDiff,
    ProjectImportDiffConflictError,
    ProjectImportDiffService,
)


def _draft(**updates: object) -> ProjectImportDraft:
    data: dict[str, object] = {
        "id": "imp_diff123",
        "project_id": "prj_diff123",
        "source_id": "src_diff123",
        "project": ProjectDraft(name="Test Project"),
        "phases": [],
        "tasks": [
            TaskDraft(
                temp_id="tmp_task_foundation",
                name="Foundation",
                description="Test description",
            )
        ],
        "dependencies": [],
        "materials": [],
        "material_requirements": [],
        "milestones": [],
        "warnings": [],
        "conflicts": [],
        "created_at": datetime.now(UTC),
    }
    data.update(updates)
    return ProjectImportDraft.model_validate(data)


def _context(
    *, tasks: tuple[Task, ...] = (), materials: tuple[Material, ...] = ()
) -> ProjectContext:
    return ProjectContext(
        project_id="prj_diff123",
        active_tasks=tasks,
        materials=materials,
        open_issues=(),
        pending_approvals=(),
    )


def test_project_import_diff_service_identifies_additions() -> None:
    diffs = ProjectImportDiffService().compare(_draft(), _context())

    assert diffs == [
        EntityDiff(
            entity_type="task",
            temp_id="tmp_task_foundation",
            entity_id=None,
            operation=DiffOperation.ADDED,
            details="Task 'Foundation' will be added.",
        )
    ]


def test_normalized_task_and_material_matches_are_blocking_changes() -> None:
    draft = _draft(
        tasks=[
            {
                "temp_id": "tmp_task_plastering",
                "name": "Ground floor plastering",
            }
        ],
        materials=[
            {
                "temp_id": "tmp_material_cement",
                "name": "cement-bags",
                "canonical_unit": "bags",
            }
        ],
    )
    context = _context(
        tasks=(
            Task(
                id="tsk_existing123",
                project_id=draft.project_id,
                title="Ground-floor plastering",
            ),
        ),
        materials=(
            Material(
                id="mat_existing123",
                project_id=draft.project_id,
                name="Cement Bags",
                normalized_name="cement bags",
                unit="bags",
            ),
        ),
    )

    diffs = ProjectImportDiffService().compare(draft, context)

    assert [(item.entity_type, item.entity_id, item.operation) for item in diffs] == [
        ("task", "tsk_existing123", DiffOperation.CHANGED),
        ("material", "mat_existing123", DiffOperation.CHANGED),
    ]


def test_multiple_normalized_canonical_matches_are_ambiguous_conflicts() -> None:
    draft = _draft()
    context = _context(
        tasks=(
            Task(
                id="tsk_existing123",
                project_id=draft.project_id,
                title="Foundation",
            ),
            Task(
                id="tsk_existing456",
                project_id=draft.project_id,
                title="foundation!",
            ),
        )
    )

    [diff] = ProjectImportDiffService().compare(draft, context)

    assert diff.operation is DiffOperation.CONFLICTED
    assert diff.entity_id is None
    assert "multiple canonical tasks" in diff.details


def test_changed_requirement_is_detected_against_canonical_task_material_pair() -> None:
    draft = _draft(
        tasks=[{"temp_id": "tmp_task_foundation", "name": "Foundation"}],
        materials=[
            {
                "temp_id": "tmp_material_cement",
                "name": "Cement",
                "canonical_unit": "bags",
            }
        ],
        material_requirements=[
            {
                "task_temp_id": "tmp_task_foundation",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("100"),
                "unit": "bags",
                "required_by": date(2026, 9, 1),
            }
        ],
    )
    task = Task(id="tsk_existing123", project_id=draft.project_id, title="Foundation")
    material = Material(
        id="mat_existing123",
        project_id=draft.project_id,
        name="Cement",
        normalized_name="cement",
        unit="bags",
    )
    requirement = MaterialRequirement(
        id="req_existing123",
        project_id=draft.project_id,
        import_id="imp_existing123",
        task_id=task.id,
        material_id=material.id,
        required_quantity=Decimal("80"),
        unit="bags",
        required_by=date(2026, 9, 1),
    )

    diffs = ProjectImportDiffService().compare(
        draft,
        _context(tasks=(task,), materials=(material,)),
        requirements=(requirement,),
    )

    requirement_diff = next(item for item in diffs if item.entity_type == "requirement")
    assert requirement_diff.operation is DiffOperation.CHANGED
    assert requirement_diff.entity_id == requirement.id
    assert "differs from the existing requirement" in requirement_diff.details


def test_additive_guard_rejects_every_non_additive_operation() -> None:
    for operation in (
        DiffOperation.CHANGED,
        DiffOperation.REMOVED,
        DiffOperation.CONFLICTED,
    ):
        diff = EntityDiff(
            entity_type="task",
            temp_id="tmp_task_foundation",
            entity_id="tsk_existing123",
            operation=operation,
            details="Unsafe reconciliation.",
        )

        with pytest.raises(ProjectImportDiffConflictError) as exc_info:
            ProjectImportDiffService.ensure_additive((diff,))

        assert exc_info.value.diffs == (diff,)


def test_phase_and_requirement_for_wholly_new_entities_remain_additive() -> None:
    draft = _draft(
        phases=[{"temp_id": "tmp_phase_one", "name": "Substructure", "sequence": 1}],
        tasks=[
            {
                "temp_id": "tmp_task_foundation",
                "name": "Foundation",
                "phase_temp_id": "tmp_phase_one",
            }
        ],
        materials=[
            {
                "temp_id": "tmp_material_cement",
                "name": "Cement",
                "canonical_unit": "bags",
            }
        ],
        material_requirements=[
            {
                "task_temp_id": "tmp_task_foundation",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("100"),
                "unit": "bags",
            }
        ],
    )

    diffs = ProjectImportDiffService().compare(
        draft,
        _context(),
        phases=(
            ProjectPhase(
                id="phs_other123",
                project_id=draft.project_id,
                import_id="imp_other123",
                name="Finishes",
                sequence=2,
            ),
        ),
    )

    assert {item.entity_type for item in diffs} == {
        "phase",
        "task",
        "material",
        "requirement",
    }
    assert {item.operation for item in diffs} == {DiffOperation.ADDED}
    ProjectImportDiffService.ensure_additive(diffs)
