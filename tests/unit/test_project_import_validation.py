from datetime import date
from decimal import Decimal

import pytest

from app.domain.project_import import DraftTaskStatus, ProjectImportDraft
from app.services.project_import_validation import (
    ProjectImportValidationError,
    ProjectImportValidator,
)


def _draft(**updates: object) -> ProjectImportDraft:
    value: dict[str, object] = {
        "id": "imp_validate123",
        "project_id": "prj_validate123",
        "source_id": "src_validate123",
        "project": {"name": "Validation residence"},
        "tasks": [
            {"temp_id": "tmp_task_one", "name": "Excavate", "planned_start": date(2026, 8, 1)},
            {"temp_id": "tmp_task_two", "name": "Foundation", "planned_finish": date(2026, 8, 8)},
        ],
        "materials": [
            {
                "temp_id": "tmp_material_cement",
                "name": "Cement",
                "canonical_unit": "bags",
                "initial_on_hand_quantity": Decimal("10"),
            }
        ],
    }
    value.update(updates)
    return ProjectImportDraft.model_validate(value)


def test_valid_draft_passes_and_unresolved_references_become_warnings() -> None:
    result = ProjectImportValidator().validate(
        _draft(unresolved_references=["August completion date"])
    )

    assert result.is_valid
    assert [warning.code for warning in result.warnings] == ["UNRESOLVED_REFERENCE"]


def test_duplicate_edges_and_cycles_fail_before_import() -> None:
    dependencies = [
        {"predecessor_temp_id": "tmp_task_one", "successor_temp_id": "tmp_task_two"},
        {"predecessor_temp_id": "tmp_task_one", "successor_temp_id": "tmp_task_two"},
        {"predecessor_temp_id": "tmp_task_two", "successor_temp_id": "tmp_task_one"},
    ]
    result = ProjectImportValidator().validate(_draft(dependencies=dependencies))

    assert not result.is_valid
    assert {error.code for error in result.errors} >= {
        "DUPLICATE_DEPENDENCY",
        "DEPENDENCY_CYCLE",
    }
    with pytest.raises(ProjectImportValidationError):
        ProjectImportValidator().validate_or_raise(_draft(dependencies=dependencies))


def test_requirement_unit_mismatch_is_deterministic() -> None:
    draft = _draft(
        material_requirements=[
            {
                "task_temp_id": "tmp_task_two",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("2"),
                "unit": "kg",
            }
        ]
    )

    result = ProjectImportValidator().validate(draft)

    assert [error.code for error in result.errors] == ["MATERIAL_UNIT_MISMATCH"]


def test_duplicate_material_requirements_are_rejected_before_commit() -> None:
    requirement = {
        "task_temp_id": "tmp_task_two",
        "material_temp_id": "tmp_material_cement",
        "required_quantity": Decimal("2"),
        "unit": "bags",
    }

    result = ProjectImportValidator().validate(
        _draft(material_requirements=[requirement, requirement.copy()])
    )

    assert [error.code for error in result.errors] == ["DUPLICATE_MATERIAL_REQUIREMENT"]


def test_unknown_dependency_and_requirement_references_are_preserved_as_conflicts() -> None:
    result = ProjectImportValidator().validate(
        _draft(
            dependencies=[
                {
                    "predecessor_temp_id": "tmp_task_missing",
                    "successor_temp_id": "tmp_task_two",
                }
            ],
            material_requirements=[
                {
                    "task_temp_id": "tmp_task_missing",
                    "material_temp_id": "tmp_material_missing",
                    "required_quantity": Decimal("2"),
                    "unit": "bags",
                }
            ],
        )
    )

    assert {error.code for error in result.errors} == {
        "UNKNOWN_PREDECESSOR",
        "UNKNOWN_REQUIREMENT_TASK",
        "UNKNOWN_REQUIREMENT_MATERIAL",
    }


def test_completed_tasks_require_an_explicit_completion_date() -> None:
    result = ProjectImportValidator().validate(
        _draft(
            tasks=[
                {
                    "temp_id": "tmp_task_one",
                    "name": "Excavate",
                    "initial_status": DraftTaskStatus.COMPLETED,
                }
            ]
        )
    )

    assert [error.code for error in result.errors] == ["COMPLETED_TASK_MISSING_DATE"]


def test_punctuation_only_task_name_variants_are_duplicate_conflicts() -> None:
    result = ProjectImportValidator().validate(
        _draft(
            tasks=[
                {"temp_id": "tmp_task_one", "name": "Ground floor plastering"},
                {"temp_id": "tmp_task_two", "name": "Ground-floor plastering"},
            ]
        )
    )

    assert [error.code for error in result.errors] == ["DUPLICATE_TASK_NAME"]


def test_semantically_distinct_task_names_are_not_merged() -> None:
    result = ProjectImportValidator().validate(
        _draft(
            tasks=[
                {"temp_id": "tmp_task_one", "name": "Ground floor plastering"},
                {"temp_id": "tmp_task_two", "name": "First floor plastering"},
            ]
        )
    )

    assert result.is_valid


def test_unknown_phase_reference_is_a_persisted_validation_conflict() -> None:
    draft = _draft(
        tasks=[
            {
                "temp_id": "tmp_task_foundation",
                "name": "Foundation",
                "phase_temp_id": "tmp_phase_missing",
            }
        ]
    )

    result = ProjectImportValidator().validate(draft)

    assert [error.code for error in result.errors] == ["UNKNOWN_TASK_PHASE"]


def test_duplicate_ids_and_self_dependencies_are_validation_conflicts() -> None:
    draft = _draft(
        tasks=[
            {"temp_id": "tmp_task_one", "name": "Excavate"},
            {"temp_id": "tmp_task_one", "name": "Pour foundation"},
        ],
        dependencies=[
            {
                "predecessor_temp_id": "tmp_task_one",
                "successor_temp_id": "tmp_task_one",
            }
        ],
    )

    result = ProjectImportValidator().validate(draft)

    assert {error.code for error in result.errors} >= {
        "DUPLICATE_TEMP_ID",
        "SELF_DEPENDENCY",
    }


def test_existing_conflicts_remain_blocking_without_being_duplicated() -> None:
    draft = _draft(
        conflicts=[
            {
                "code": "EXISTING_TASK_POSSIBLE_MATCH",
                "message": "Review the possible existing task match.",
            }
        ],
        unresolved_references=["Foundation foreman"],
    )
    validator = ProjectImportValidator()

    first = validator.validate(draft)
    second = validator.validate(first.draft)

    assert not first.is_valid
    assert [error.code for error in first.errors] == ["EXISTING_TASK_POSSIBLE_MATCH"]
    assert [error.code for error in second.errors] == ["EXISTING_TASK_POSSIBLE_MATCH"]
    assert [warning.code for warning in second.warnings] == ["UNRESOLVED_REFERENCE"]
    with pytest.raises(ProjectImportValidationError) as exc_info:
        validator.validate_or_raise(first.draft)
    assert [error.code for error in exc_info.value.errors] == ["EXISTING_TASK_POSSIBLE_MATCH"]


def test_transaction_budget_counts_task_creation_activities() -> None:
    draft = _draft(
        tasks=[
            {"temp_id": f"tmp_task_{index:03d}", "name": f"Task {index:03d}"}
            for index in range(225)
        ],
        materials=[],
    )

    result = ProjectImportValidator().validate(draft)

    assert [error.code for error in result.errors] == ["TRANSACTION_WRITE_BUDGET_EXCEEDED"]


def test_prepared_plan_counts_every_atomic_commit_write() -> None:
    draft = _draft(
        phases=[{"temp_id": "tmp_phase_one", "name": "Substructure", "sequence": 1}],
        dependencies=[
            {
                "predecessor_temp_id": "tmp_task_one",
                "successor_temp_id": "tmp_task_two",
            }
        ],
        material_requirements=[
            {
                "task_temp_id": "tmp_task_two",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("2"),
                "unit": "bags",
            }
        ],
        milestones=[
            {
                "temp_id": "tmp_milestone_one",
                "name": "Substructure complete",
                "planned_date": date(2026, 8, 9),
            }
        ],
    )

    result = ProjectImportValidator().validate(draft)

    assert result.is_valid
    assert result.plan.provenance_write_count == 8
    assert result.plan.canonical_write_count == 8
    assert result.plan.activity_write_count == 7
    assert result.plan.import_state_write_count == 1
    assert result.plan.commit_write_count == 24


def test_oversized_import_record_is_a_blocking_conflict_without_discarding_draft() -> None:
    tasks = [
        {
            "temp_id": f"tmp_task_{index:03d}",
            "name": f"Task {index:03d}",
            "description": "x" * 10_000,
        }
        for index in range(75)
    ]

    result = ProjectImportValidator().validate(_draft(tasks=tasks, materials=[]))
    replay = ProjectImportValidator().validate(result.draft)

    assert [error.code for error in result.errors] == ["IMPORT_DOCUMENT_SIZE_EXCEEDED"]
    assert [error.code for error in replay.errors] == ["IMPORT_DOCUMENT_SIZE_EXCEEDED"]
    assert len(result.draft.tasks) == 75
    assert result.plan.largest_document_bytes > result.plan.limits.max_document_bytes
