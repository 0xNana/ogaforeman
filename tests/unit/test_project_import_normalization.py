from decimal import Decimal

import pytest

from app.services.project_import_extraction import ProjectImportCandidate
from app.domain.project_import import SourceType
from app.services.project_import_normalization import (
    ProjectImportNormalizer,
    normalize_task_name_for_match,
)


def _candidate(*, material_unit: str, requirement_unit: str) -> ProjectImportCandidate:
    return ProjectImportCandidate.model_validate(
        {
            "project": {"name": "Normalization residence"},
            "tasks": [{"temp_id": "tmp_task_plastering", "name": "Ground-floor plastering"}],
            "materials": [
                {
                    "temp_id": "tmp_material_cement",
                    "name": "Cement",
                    "canonical_unit": material_unit,
                    "initial_on_hand_quantity": Decimal("10"),
                }
            ],
            "material_requirements": [
                {
                    "task_temp_id": "tmp_task_plastering",
                    "material_temp_id": "tmp_material_cement",
                    "required_quantity": Decimal("20"),
                    "unit": requirement_unit,
                }
            ],
        }
    )


@pytest.mark.parametrize("unit", ["pcs", "piece", "pieces", "pices"])
def test_normalizer_converts_piece_aliases_to_canonical_units(unit: str) -> None:
    normalized = ProjectImportNormalizer().normalize(
        _candidate(material_unit=unit, requirement_unit=unit)
    )

    assert normalized.materials[0].canonical_unit == "pieces"
    assert normalized.material_requirements[0].unit == "pieces"


@pytest.mark.parametrize("unit", ["m³", "m3", "cubic metres"])
def test_normalizer_converts_cubic_metre_aliases_to_canonical_units(unit: str) -> None:
    normalized = ProjectImportNormalizer().normalize(
        _candidate(material_unit=unit, requirement_unit=unit)
    )

    assert normalized.materials[0].canonical_unit == "m3"
    assert normalized.material_requirements[0].unit == "m3"


def test_task_name_key_matches_punctuation_variants_without_semantic_merging() -> None:
    assert normalize_task_name_for_match(
        "Ground floor plastering"
    ) == normalize_task_name_for_match("Ground-floor plastering")
    assert normalize_task_name_for_match(
        "Ground floor plastering"
    ) != normalize_task_name_for_match("First floor plastering")


def test_extraction_source_references_are_temporary_and_bound_to_persisted_source() -> None:
    candidate = ProjectImportCandidate.model_validate(
        {
            "project": {"name": "Normalization residence"},
            "tasks": [
                {
                    "temp_id": "tmp_task_foundation",
                    "name": "Foundation",
                    "source_reference": {
                        "source_id": "tmp_source_section",
                        "source_type": SourceType.MARKDOWN,
                        "source_name": "plan.md",
                    },
                }
            ],
        }
    )

    normalized = ProjectImportNormalizer().normalize(candidate, source_id="src_import123")

    assert normalized.tasks[0].source_reference is not None
    assert normalized.tasks[0].source_reference.source_id == "src_import123"


def test_extraction_rejects_canonical_source_references() -> None:
    with pytest.raises(ValueError, match="temporary IDs"):
        ProjectImportCandidate.model_validate(
            {
                "project": {"name": "Normalization residence"},
                "tasks": [
                    {
                        "temp_id": "tmp_task_foundation",
                        "name": "Foundation",
                        "source_reference": {
                            "source_id": "src_other123",
                            "source_type": SourceType.MARKDOWN,
                            "source_name": "other.md",
                        },
                    }
                ],
            }
        )
