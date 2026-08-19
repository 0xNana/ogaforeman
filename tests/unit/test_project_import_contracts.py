from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.project_import import DraftTaskStatus, ProjectImportDraft, SourceType
from app.services.project_import_validation import ProjectImportValidator


def _source() -> dict[str, object]:
    return {
        "source_id": "src_residential123",
        "source_type": SourceType.MARKDOWN,
        "source_name": "residential-plan.md",
        "section": "Finishes",
        "imported_at": datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
    }


def test_complete_residential_fixture_validates_without_gemini() -> None:
    draft = ProjectImportDraft.model_validate(
        {
            "schema_version": 1,
            "id": "imp_residential123",
            "project_id": "prj_residential123",
            "source_id": "src_residential123",
            "project": {
                "name": "Three-bedroom residence",
                "type": "residential",
                "location": "Accra",
                "start_date": date(2026, 8, 20),
                "target_end_date": date(2027, 2, 20),
            },
            "phases": [
                {"temp_id": "tmp_phase_substructure", "name": "Substructure", "sequence": 1},
                {"temp_id": "tmp_phase_finishes", "name": "Finishes", "sequence": 2},
            ],
            "tasks": [
                {
                    "temp_id": "tmp_task_foundation",
                    "name": "Foundation",
                    "phase_temp_id": "tmp_phase_substructure",
                    "planned_start": date(2026, 8, 20),
                    "planned_finish": date(2026, 8, 30),
                    "initial_status": DraftTaskStatus.PLANNED,
                    "source_reference": _source(),
                },
                {
                    "temp_id": "tmp_task_plastering",
                    "name": "Ground-floor plastering",
                    "phase_temp_id": "tmp_phase_finishes",
                    "planned_start": date(2026, 10, 1),
                    "planned_finish": date(2026, 10, 10),
                    "trade": "Masonry",
                    "source_reference": _source(),
                },
            ],
            "dependencies": [
                {
                    "predecessor_temp_id": "tmp_task_foundation",
                    "successor_temp_id": "tmp_task_plastering",
                    "source_reference": _source(),
                }
            ],
            "materials": [
                {
                    "temp_id": "tmp_material_cement",
                    "name": "Cement",
                    "canonical_unit": "bags",
                    "initial_on_hand_quantity": Decimal("10"),
                    "source_reference": _source(),
                }
            ],
            "material_requirements": [
                {
                    "task_temp_id": "tmp_task_plastering",
                    "material_temp_id": "tmp_material_cement",
                    "required_quantity": Decimal("100"),
                    "unit": "bags",
                    "required_by": date(2026, 10, 1),
                    "confidence": Decimal("0.98"),
                    "source_reference": _source(),
                }
            ],
        }
    )

    assert draft.schema_version == 1
    assert draft.tasks[1].temp_id == "tmp_task_plastering"
    assert draft.material_requirements[0].required_quantity == Decimal("100")


def test_contract_rejects_canonical_ids_for_draft_entities() -> None:
    with pytest.raises(ValidationError, match="temp_id"):
        ProjectImportDraft(
            id="imp_residential123",
            project_id="prj_residential123",
            source_id="src_residential123",
            project={"name": "Residence"},
            tasks=[{"temp_id": "tsk_canonical123", "name": "Foundation"}],
        )


def test_contract_preserves_unknown_references_for_deterministic_validation() -> None:
    draft = ProjectImportDraft(
        id="imp_residential123",
        project_id="prj_residential123",
        source_id="src_residential123",
        project={"name": "Residence"},
        tasks=[
            {
                "temp_id": "tmp_task_foundation",
                "name": "Foundation",
                "phase_temp_id": "tmp_missing_phase",
            }
        ],
    )

    result = ProjectImportValidator().validate(draft)

    assert draft.tasks[0].phase_temp_id == "tmp_missing_phase"
    assert [error.code for error in result.errors] == ["UNKNOWN_TASK_PHASE"]


def test_contract_rejects_noncanonical_units() -> None:

    with pytest.raises(ValidationError, match="canonical_unit"):
        ProjectImportDraft(
            id="imp_residential123",
            project_id="prj_residential123",
            source_id="src_residential123",
            project={"name": "Residence"},
            materials=[
                {
                    "temp_id": "tmp_material_cement",
                    "name": "Cement",
                    "canonical_unit": "bag",
                }
            ],
        )


def test_contract_rejects_invalid_quantity() -> None:
    with pytest.raises(ValidationError, match="required_quantity"):
        ProjectImportDraft(
            id="imp_residential123",
            project_id="prj_residential123",
            source_id="src_residential123",
            project={"name": "Residence"},
            tasks=[{"temp_id": "tmp_task_1", "name": "Task"}],
            materials=[{"temp_id": "tmp_mat_1", "name": "Mat", "canonical_unit": "pieces"}],
            material_requirements=[
                {
                    "task_temp_id": "tmp_task_1",
                    "material_temp_id": "tmp_mat_1",
                    "required_quantity": Decimal("-10"),
                    "unit": "pieces",
                }
            ],
        )
