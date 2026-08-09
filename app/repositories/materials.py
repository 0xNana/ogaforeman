"""Authorized material identity and append-only ledger repositories."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.materials import MaterialLedgerEntry, normalize_material_name
from app.domain.models import Material
from app.repositories.interfaces import (
    EntityNotFoundError,
    ProjectRepository,
    RepositorySession,
    RepositoryStore,
)
from app.repositories.membership import AuthorizedProjectRepository


class MaterialIdentityConflictError(ValueError):
    code = "CONFLICT_MATERIAL_ALIAS"


class MaterialRepository:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, access: ProjectAccessContext, material_id: str) -> Material | None:
        return self.for_session(self._store, access).get(access.project_id, material_id)

    def list(self, access: ProjectAccessContext) -> Sequence[Material]:
        return self.for_session(self._store, access).list(access.project_id)

    def resolve(self, access: ProjectAccessContext, material_id_or_alias: str) -> Material:
        return self.resolve_in(
            self.for_session(self._store, access), access.project_id, material_id_or_alias
        )

    @staticmethod
    def for_session(
        session: RepositorySession,
        access: ProjectAccessContext,
    ) -> ProjectRepository[Material]:
        return AuthorizedProjectRepository(
            session.repository(Material),
            access,
            mutation_permission=ProjectPermission.OPERATE,
        )

    @staticmethod
    def resolve_in(
        repository: ProjectRepository[Material],
        project_id: str,
        material_id_or_alias: str,
    ) -> Material:
        direct = repository.get(project_id, material_id_or_alias)
        if direct is not None:
            return direct
        normalized = normalize_material_name(material_id_or_alias)
        matches = [
            material
            for material in repository.list(project_id)
            if normalized
            in {
                material.normalized_name,
                normalize_material_name(material.name),
                *(normalize_material_name(alias) for alias in material.aliases),
            }
        ]
        if not matches:
            raise EntityNotFoundError(
                f"material {material_id_or_alias} was not found in project {project_id}"
            )
        if len(matches) > 1:
            raise MaterialIdentityConflictError(
                f"material alias {material_id_or_alias} is ambiguous"
            )
        return matches[0]


class MaterialLedgerRepository:
    """Append-only access to quantity ledger entries."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(
        self,
        access: ProjectAccessContext,
        ledger_entry_id: str,
    ) -> MaterialLedgerEntry | None:
        return self.for_session(self._store, access).get(access.project_id, ledger_entry_id)

    def list(self, access: ProjectAccessContext) -> Sequence[MaterialLedgerEntry]:
        return self.for_session(self._store, access).list(access.project_id)

    @staticmethod
    def for_session(
        session: RepositorySession,
        access: ProjectAccessContext,
    ) -> ProjectRepository[MaterialLedgerEntry]:
        return AuthorizedProjectRepository(
            session.repository(MaterialLedgerEntry),
            access,
            mutation_permission=ProjectPermission.OPERATE,
        )


__all__ = [
    "MaterialIdentityConflictError",
    "MaterialLedgerRepository",
    "MaterialRepository",
]
