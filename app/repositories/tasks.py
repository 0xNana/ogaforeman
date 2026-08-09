"""Authorized repository boundary for project tasks."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.models import Task
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore
from app.repositories.membership import AuthorizedProjectRepository


class TaskRepository:
    """Resolve tasks only through an already-authorized project context."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, access: ProjectAccessContext, task_id: str) -> Task | None:
        return self._authorized(self._store.repository(Task), access).get(
            access.project_id, task_id
        )

    def require(self, access: ProjectAccessContext, task_id: str) -> Task:
        return self._authorized(self._store.repository(Task), access).require(
            access.project_id, task_id
        )

    def list(self, access: ProjectAccessContext) -> Sequence[Task]:
        return self._authorized(self._store.repository(Task), access).list(access.project_id)

    @staticmethod
    def for_session(
        session: RepositorySession,
        access: ProjectAccessContext,
    ) -> ProjectRepository[Task]:
        return TaskRepository._authorized(session.repository(Task), access)

    @staticmethod
    def _authorized(
        repository: ProjectRepository[Task],
        access: ProjectAccessContext,
    ) -> ProjectRepository[Task]:
        return AuthorizedProjectRepository(
            repository,
            access,
            mutation_permission=ProjectPermission.OPERATE,
        )


__all__ = ["TaskRepository"]
