"""Authorized lookup of trusted project-import provenance."""

from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.import_records import (
    ImportProvenance,
    ImportProvenanceTargetType,
    import_dependency_target_id,
    import_provenance_id,
)
from app.repositories.interfaces import RepositoryStore
from app.repositories.membership import AuthorizedProjectRepository


class ProjectImportProvenanceNotFoundError(LookupError):
    code = "PROJECT_IMPORT_PROVENANCE_NOT_FOUND"


class ProjectImportProvenanceService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(
        self,
        access: ProjectAccessContext,
        provenance_id: str,
    ) -> ImportProvenance:
        ensure_permission(access, ProjectPermission.READ)
        provenance = self._repository(access).get(access.project_id, provenance_id)
        if provenance is None:
            raise ProjectImportProvenanceNotFoundError("project import provenance was not found")
        return provenance

    def get_for_target(
        self,
        access: ProjectAccessContext,
        *,
        target_entity_type: ImportProvenanceTargetType,
        target_entity_id: str,
    ) -> ImportProvenance:
        provenance = self.get(
            access,
            import_provenance_id(target_entity_type, target_entity_id),
        )
        if (
            provenance is None
            or provenance.target_entity_type is not target_entity_type
            or provenance.target_entity_id != target_entity_id
        ):
            raise ProjectImportProvenanceNotFoundError("project import provenance was not found")
        return provenance

    def get_for_dependency(
        self,
        access: ProjectAccessContext,
        *,
        predecessor_task_id: str,
        successor_task_id: str,
    ) -> ImportProvenance:
        return self.get_for_target(
            access,
            target_entity_type=ImportProvenanceTargetType.DEPENDENCY,
            target_entity_id=import_dependency_target_id(
                predecessor_task_id,
                successor_task_id,
            ),
        )

    def _repository(
        self,
        access: ProjectAccessContext,
    ) -> AuthorizedProjectRepository[ImportProvenance]:
        return AuthorizedProjectRepository(
            self._store.repository(ImportProvenance),
            access,
        )


__all__ = [
    "ProjectImportProvenanceNotFoundError",
    "ProjectImportProvenanceService",
]
