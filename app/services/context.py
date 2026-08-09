"""Bounded project context service."""

from app.domain.authorization import ProjectAccessContext
from app.repositories.context import ContextRepository, ProjectContext


class ContextService:
    def __init__(self, context_repo: ContextRepository) -> None:
        self._context_repo = context_repo

    def get_context(self, access: ProjectAccessContext) -> ProjectContext:
        return self._context_repo.get_bounded_context(access)
