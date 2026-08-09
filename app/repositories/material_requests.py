from collections.abc import Sequence
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.models import MaterialRequest
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore
from app.repositories.membership import AuthorizedProjectRepository


class MaterialRequestRepository:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, access: ProjectAccessContext, request_id: str) -> MaterialRequest | None:
        return self.for_session(self._store, access).get(access.project_id, request_id)

    def list(self, access: ProjectAccessContext) -> Sequence[MaterialRequest]:
        return self.for_session(self._store, access).list(access.project_id)

    @staticmethod
    def for_session(
        session: RepositorySession,
        access: ProjectAccessContext,
    ) -> ProjectRepository[MaterialRequest]:
        return AuthorizedProjectRepository(
            session.repository(MaterialRequest),
            access,
            mutation_permission=ProjectPermission.OPERATE,
        )


__all__ = ["MaterialRequestRepository"]
