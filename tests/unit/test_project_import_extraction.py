import asyncio
from decimal import Decimal

import pytest

from app.domain.import_records import ProjectImportRecord
from app.services.project_import_extraction import (
    ProjectImportExtractionService,
    ProjectImportCandidate,
    ProjectImportModelUnavailableError,
)
from app.domain.project_import import (
    PROJECT_IMPORT_STATUS_TRANSITIONS,
    DraftTaskStatus,
    ProjectImportStatus,
)


class FakeProjectExtractor:
    model_id = "fixture-gemini-model"

    async def extract(self, source_text: str) -> ProjectImportCandidate:
        assert "Foundation" in source_text
        return ProjectImportCandidate.model_validate(
            {
                "project": {"name": "Imported residence"},
                "phases": [{"temp_id": "tmp_phase_one", "name": "Substructure", "sequence": 1}],
                "tasks": [
                    {
                        "temp_id": "tmp_task_foundation",
                        "name": "Foundation",
                        "phase_temp_id": "tmp_phase_one",
                        "initial_status": DraftTaskStatus.PLANNED,
                    }
                ],
                "materials": [],
            }
        )


class AliasUnitProjectExtractor:
    async def extract(self, source_text: str) -> ProjectImportCandidate:
        return ProjectImportCandidate.model_validate(
            {
                "project": {"name": "Imported residence"},
                "tasks": [{"temp_id": "tmp_task_foundation", "name": "Foundation"}],
                "materials": [
                    {
                        "temp_id": "tmp_material_cement",
                        "name": "Cement",
                        "canonical_unit": "pices",
                        "initial_on_hand_quantity": Decimal("10"),
                    }
                ],
                "material_requirements": [
                    {
                        "task_temp_id": "tmp_task_foundation",
                        "material_temp_id": "tmp_material_cement",
                        "required_quantity": Decimal("2"),
                        "unit": "pcs",
                    }
                ],
            }
        )


class SlowProjectExtractor:
    async def extract(self, source_text: str) -> ProjectImportCandidate:
        del source_text
        await asyncio.sleep(0.05)
        raise AssertionError("bounded extraction should time out first")


def test_project_import_status_transition_table_is_complete_and_terminal_safe() -> None:
    assert PROJECT_IMPORT_STATUS_TRANSITIONS == {
        ProjectImportStatus.UPLOADED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.EXTRACTING: frozenset(
            {
                ProjectImportStatus.DRAFT,
                ProjectImportStatus.EXTRACTION_FAILED,
                ProjectImportStatus.CANCELLED,
            }
        ),
        ProjectImportStatus.DRAFT: frozenset(
            {ProjectImportStatus.VALIDATING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.VALIDATING: frozenset(
            {
                ProjectImportStatus.NEEDS_REVIEW,
                ProjectImportStatus.VALIDATION_FAILED,
                ProjectImportStatus.CANCELLED,
            }
        ),
        ProjectImportStatus.NEEDS_REVIEW: frozenset(
            {ProjectImportStatus.CONFIRMED, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.CONFIRMED: frozenset({ProjectImportStatus.IMPORTING}),
        ProjectImportStatus.IMPORTING: frozenset(
            {ProjectImportStatus.IMPORTED, ProjectImportStatus.IMPORT_FAILED}
        ),
        ProjectImportStatus.EXTRACTION_FAILED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.VALIDATION_FAILED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.IMPORT_FAILED: frozenset(
            {ProjectImportStatus.IMPORTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.IMPORTED: frozenset(),
        ProjectImportStatus.CANCELLED: frozenset(),
    }


@pytest.mark.asyncio
async def test_project_import_extraction_service_returns_a_scoped_typed_draft() -> None:
    service = ProjectImportExtractionService(FakeProjectExtractor())

    draft = await service.extract(
        project_id="prj_extract123",
        import_id="imp_extract123",
        source_id="src_extract123",
        source_text="Task: Foundation",
    )

    assert draft.id == "imp_extract123"
    assert draft.project_id == "prj_extract123"
    assert draft.source_id == "src_extract123"
    assert draft.status is ProjectImportStatus.NEEDS_REVIEW
    assert draft.tasks[0].name == "Foundation"
    assert service.model_id == "fixture-gemini-model"


@pytest.mark.asyncio
async def test_extraction_service_normalizes_gemini_unit_aliases() -> None:
    service = ProjectImportExtractionService(AliasUnitProjectExtractor())

    draft = await service.extract(
        project_id="prj_extract123",
        import_id="imp_extract123",
        source_id="src_extract123",
        source_text="Task: Foundation",
    )

    assert draft.materials[0].canonical_unit == "pieces"
    assert draft.material_requirements[0].unit == "pieces"


@pytest.mark.asyncio
async def test_project_import_extraction_requires_no_adk_session_state() -> None:
    service = ProjectImportExtractionService(FakeProjectExtractor())

    draft = await service.extract(
        project_id="prj_extract123",
        import_id="imp_executor123",
        source_id="src_executor123",
        source_text="Task: Foundation",
    )

    assert draft.id == "imp_executor123"
    assert "extraction_session_id" not in ProjectImportRecord.model_fields
    assert "extraction_invocation_id" not in ProjectImportRecord.model_fields


@pytest.mark.asyncio
async def test_project_import_extraction_is_time_bounded() -> None:
    service = ProjectImportExtractionService(SlowProjectExtractor(), timeout_seconds=0.001)

    with pytest.raises(ProjectImportModelUnavailableError, match="timed out"):
        await service.extract(
            project_id="prj_extract123",
            import_id="imp_timeout123",
            source_id="src_timeout123",
            source_text="Task: Foundation",
        )
