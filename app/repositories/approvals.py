"""Authorized repository boundary for approvals."""

from collections.abc import Sequence
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.models import Approval
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore
from app.repositories.membership import AuthorizedProjectRepository


class ApprovalRepository:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, access: ProjectAccessContext, approval_id: str) -> Approval | None:
        return self.for_session(self._store, access).get(access.project_id, approval_id)

    def list(self, access: ProjectAccessContext) -> Sequence[Approval]:
        return self.for_session(self._store, access).list(access.project_id)

    @staticmethod
    def for_session(
        session: RepositorySession,
        access: ProjectAccessContext,
    ) -> ProjectRepository[Approval]:
        return AuthorizedProjectRepository(
            session.repository(Approval),
            access,
            mutation_permission=ProjectPermission.OPERATE,
        )


__all__ = ["ApprovalRepository"]
