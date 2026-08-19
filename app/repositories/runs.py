"""Authorized repository boundary for agent runs."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Callable, TypeVar

from app.domain.models import AgentRun
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore

ResultT = TypeVar("ResultT")


def run_id_for_event(event_id: str) -> str:
    return f"run_{sha256(event_id.encode('utf-8')).hexdigest()[:32]}"


class AgentRunRepository:
    """Repository boundary for agent runs."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, project_id: str, run_id: str) -> AgentRun | None:
        return self._store.repository(AgentRun).get(project_id, run_id)

    def require(self, project_id: str, run_id: str) -> AgentRun:
        return self._store.repository(AgentRun).require(project_id, run_id)

    def list(self, project_id: str) -> Sequence[AgentRun]:
        return self._store.repository(AgentRun).list(project_id)

    def create(self, run: AgentRun) -> AgentRun:
        return self._store.repository(AgentRun).create(run)

    def save(self, run: AgentRun, *, expected_version: int | None = None) -> AgentRun:
        return self._store.repository(AgentRun).save(run, expected_version=expected_version)

    def run_transaction(self, operation: Callable[[RepositorySession], ResultT]) -> ResultT:
        return self._store.run_transaction(operation)

    @staticmethod
    def for_session(
        session: RepositorySession,
    ) -> ProjectRepository[AgentRun]:
        return session.repository(AgentRun)


__all__ = ["AgentRunRepository", "run_id_for_event"]
