from datetime import UTC, datetime

import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import MemberRole
from app.domain.import_records import (
    ImportProvenance,
    ImportProvenanceTargetType,
    import_provenance_id,
)
from app.domain.project_import import SourceType
from app.repositories.memory import InMemoryRepositoryStore
from app.services.project_import_provenance import (
    ProjectImportProvenanceNotFoundError,
    ProjectImportProvenanceService,
)


def _access(project_id: str = "prj_provenance123") -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_reader123", subject="test"),
        project_id=project_id,
        role=MemberRole.VIEWER,
    )


def _provenance(project_id: str = "prj_provenance123") -> ImportProvenance:
    return ImportProvenance(
        id=import_provenance_id(
            ImportProvenanceTargetType.TASK,
            "tsk_foundation123",
        ),
        project_id=project_id,
        import_id="imp_provenance123",
        source_id="src_provenance123",
        source_checksum="a" * 64,
        source_type=SourceType.MARKDOWN,
        source_name="trusted-plan.md",
        target_entity_type=ImportProvenanceTargetType.TASK,
        target_entity_id="tsk_foundation123",
        section="Substructure",
        external_reference="row-12",
        imported_by="usr_admin123",
        imported_at=datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
        idempotency_key="project-import:provenance:task",
    )


def test_provenance_lookup_resolves_trusted_source_and_import_links() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ImportProvenance).create(_provenance())

    result = ProjectImportProvenanceService(store).get_for_target(
        _access(),
        target_entity_type=ImportProvenanceTargetType.TASK,
        target_entity_id="tsk_foundation123",
    )

    assert result.import_id == "imp_provenance123"
    assert result.source_id == "src_provenance123"
    assert result.source_checksum == "a" * 64
    assert result.source_name == "trusted-plan.md"
    assert ProjectImportProvenanceService(store).get(_access(), result.id) == result


def test_provenance_lookup_does_not_leak_another_project() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ImportProvenance).create(_provenance("prj_other123"))

    with pytest.raises(ProjectImportProvenanceNotFoundError):
        ProjectImportProvenanceService(store).get_for_target(
            _access(),
            target_entity_type=ImportProvenanceTargetType.TASK,
            target_entity_id="tsk_foundation123",
        )
