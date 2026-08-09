from collections.abc import Sequence
from typing import Callable, Generic, Protocol, TypeVar

from pydantic import BaseModel


class RepositoryError(RuntimeError):
    """Base error for repository contract failures."""


class EntityAlreadyExistsError(RepositoryError):
    """Raised when a create operation would overwrite an existing entity."""


class EntityNotFoundError(RepositoryError):
    """Raised when a required entity does not exist in the project partition."""


class VersionConflictError(RepositoryError):
    """Raised when an optimistic-concurrency precondition does not hold."""


EntityT = TypeVar("EntityT", bound=BaseModel)
ResultT = TypeVar("ResultT")


class RepositoryTransaction(Protocol, Generic[EntityT]):
    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        """Return a detached entity or ``None`` inside this transaction."""

    def require(self, project_id: str, entity_id: str) -> EntityT:
        """Return a detached entity or raise ``EntityNotFoundError``."""

    def list(self, project_id: str) -> Sequence[EntityT]:
        """Return detached entities from one project partition."""

    def create(self, entity: EntityT) -> EntityT:
        """Create an entity without replacing an existing ID."""

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        """Replace an entity after an optimistic-concurrency check."""

    def delete(
        self, project_id: str, entity_id: str, *, expected_version: int | None = None
    ) -> None:
        """Delete an entity after a matching optimistic-concurrency check."""

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        """Return the repository revision for an entity, if it exists."""


class ProjectRepository(Protocol, Generic[EntityT]):
    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        """Return a detached entity or ``None`` inside this project partition."""

    def require(self, project_id: str, entity_id: str) -> EntityT:
        """Return a detached entity or raise ``EntityNotFoundError``."""

    def list(self, project_id: str) -> Sequence[EntityT]:
        """Return detached entities from one project partition."""

    def create(self, entity: EntityT) -> EntityT:
        """Create an entity without replacing an existing ID."""

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        """Replace an entity after an optimistic-concurrency check."""

    def delete(
        self, project_id: str, entity_id: str, *, expected_version: int | None = None
    ) -> None:
        """Delete an entity after a matching optimistic-concurrency check."""

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        """Return the repository revision for an entity, if it exists."""

    def run_transaction(
        self,
        operation: Callable[[RepositoryTransaction[EntityT]], ResultT],
    ) -> ResultT:
        """Run and, where supported, retry one atomic collection operation."""


class RepositorySession(Protocol):
    def repository(self, entity_type: type[EntityT]) -> ProjectRepository[EntityT]:
        """Return the typed repository for an entity collection."""


class OutboxRepository(ProjectRepository[EntityT], Protocol):
    def get_pending(self, limit: int = 100) -> Sequence[EntityT]:
        """Return pending outbox messages across all projects."""


class RepositoryStore(RepositorySession, Protocol):
    def run_transaction(self, operation: Callable[[RepositorySession], ResultT]) -> ResultT:
        """Run and, where supported, retry one atomic cross-collection operation."""
