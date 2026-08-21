from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from threading import RLock
from types import TracebackType
from typing import Any, Callable, Generic, TypeVar, cast

from pydantic import BaseModel

from app.domain.models import Project

from .interfaces import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    ProjectRepository,
    RepositorySession,
    RepositoryStore,
    RepositoryTransaction,
    VersionConflictError,
)


EntityT = TypeVar("EntityT", bound=BaseModel)
ResultT = TypeVar("ResultT")
_Record = tuple[EntityT, int]


class InMemoryRepository(Generic[EntityT], ProjectRepository[EntityT]):
    """Isolated, lock-protected repository used by unit and contract tests.

    The instance owns all state. It has no module-level collection, so each test or
    application composition gets an explicit state boundary that can later be replaced
    by a Firestore-backed implementation.
    """

    def __init__(self, entity_type: type[EntityT], *, _lock: RLock | None = None) -> None:
        self._entity_type = entity_type
        self._records: dict[str, dict[str, _Record[EntityT]]] = {}
        self._lock = _lock or RLock()

    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        with self._lock:
            record = self._records.get(project_id, {}).get(entity_id)
            return self._copy_entity(record[0]) if record else None

    def require(self, project_id: str, entity_id: str) -> EntityT:
        entity = self.get(project_id, entity_id)
        if entity is None:
            raise EntityNotFoundError(f"entity {entity_id} was not found in project {project_id}")
        return entity

    def list(self, project_id: str) -> Sequence[EntityT]:
        with self._lock:
            records = self._records.get(project_id, {})
            return tuple(self._copy_entity(records[entity_id][0]) for entity_id in sorted(records))

    def create(self, entity: EntityT) -> EntityT:
        project_id, entity_id = self._identity(entity)
        with self._lock:
            project_records = self._records.setdefault(project_id, {})
            if entity_id in project_records:
                raise EntityAlreadyExistsError(
                    f"entity {entity_id} already exists in project {project_id}"
                )
            validated = self._validate_for_create(entity)
            project_records[entity_id] = (validated, 0)
            return self._copy_entity(validated)

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        project_id, entity_id = self._identity(entity)
        with self._lock:
            project_records = self._records.get(project_id, {})
            current = project_records.get(entity_id)
            if current is None:
                raise EntityNotFoundError(
                    f"entity {entity_id} was not found in project {project_id}"
                )
            _, current_version = current
            self._require_expected_version(expected_version, current_version)
            next_version = current_version + 1
            validated = self._validate_with_version(entity, next_version)
            project_records[entity_id] = (validated, next_version)
            return self._copy_entity(validated)

    def delete(
        self,
        project_id: str,
        entity_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        with self._lock:
            project_records = self._records.get(project_id, {})
            current = project_records.get(entity_id)
            if current is None:
                raise EntityNotFoundError(
                    f"entity {entity_id} was not found in project {project_id}"
                )
            self._require_expected_version(expected_version, current[1])
            del project_records[entity_id]
            if not project_records:
                self._records.pop(project_id, None)

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        with self._lock:
            record = self._records.get(project_id, {}).get(entity_id)
            return record[1] if record else None

    def transaction(self) -> _MemoryTransaction[EntityT]:
        return _MemoryTransaction(self)

    def run_transaction(
        self,
        operation: Callable[[RepositoryTransaction[EntityT]], ResultT],
    ) -> ResultT:
        with self.transaction() as transaction:
            return operation(transaction)

    def _identity(self, entity: EntityT) -> tuple[str, str]:
        project_id = getattr(entity, "project_id", None)
        entity_id = getattr(entity, "id", None)
        if isinstance(entity, Project):
            project_id = entity.id
        if not isinstance(project_id, str) or not isinstance(entity_id, str):
            raise TypeError("repository entities must expose string id and project_id fields")
        return project_id, entity_id

    def _validate(self, entity: EntityT) -> EntityT:
        return self._entity_type.model_validate(entity.model_dump())

    def _validate_for_create(self, entity: EntityT) -> EntityT:
        validated = self._validate(entity)
        if "version" in self._entity_type.model_fields and getattr(validated, "version") != 0:
            raise VersionConflictError("new repository entities must start at version 0")
        return validated

    def _validate_with_version(self, entity: EntityT, version: int) -> EntityT:
        data: dict[str, Any] = entity.model_dump()
        if "version" in self._entity_type.model_fields:
            data["version"] = version
        return self._entity_type.model_validate(data)

    @staticmethod
    def _copy_entity(entity: EntityT) -> EntityT:
        return deepcopy(entity)

    @staticmethod
    def _require_expected_version(expected_version: int | None, current_version: int) -> None:
        if expected_version is None:
            raise VersionConflictError("expected_version is required for updates and deletes")
        if expected_version != current_version:
            raise VersionConflictError(
                f"expected_version {expected_version} does not match current version {current_version}"
            )


class _MemoryTransaction(Generic[EntityT], RepositoryTransaction[EntityT]):
    def __init__(self, repository: InMemoryRepository[EntityT]) -> None:
        self._repository = repository
        self._snapshot: dict[str, dict[str, _Record[EntityT]]] | None = None

    def __enter__(self) -> "_MemoryTransaction[EntityT]":
        self._repository._lock.acquire()
        self._snapshot = deepcopy(self._repository._records)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None and self._snapshot is not None:
                self._repository._records = self._snapshot
        finally:
            self._repository._lock.release()

    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        return self._repository.get(project_id, entity_id)

    def require(self, project_id: str, entity_id: str) -> EntityT:
        return self._repository.require(project_id, entity_id)

    def list(self, project_id: str) -> Sequence[EntityT]:
        return self._repository.list(project_id)

    def create(self, entity: EntityT) -> EntityT:
        return self._repository.create(entity)

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        return self._repository.save(entity, expected_version=expected_version)

    def delete(
        self,
        project_id: str,
        entity_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        self._repository.delete(project_id, entity_id, expected_version=expected_version)

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        return self._repository.version_of(project_id, entity_id)


class InMemoryRepositoryStore(RepositoryStore):
    """Owns isolated repositories and coordinates atomic cross-collection transactions."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._repositories: dict[type[BaseModel], InMemoryRepository[BaseModel]] = {}

    def repository(self, entity_type: type[EntityT]) -> InMemoryRepository[EntityT]:
        with self._lock:
            repository = self._repositories.get(entity_type)
            if repository is None:
                repository = InMemoryRepository(
                    cast(type[BaseModel], entity_type),
                    _lock=self._lock,
                )
                self._repositories[entity_type] = repository
            return cast(InMemoryRepository[EntityT], repository)

    def transaction(self) -> _MemoryStoreTransaction:
        return _MemoryStoreTransaction(self)

    def run_transaction(self, operation: Callable[[RepositorySession], ResultT]) -> ResultT:
        with self.transaction() as transaction:
            return operation(transaction)


class _MemoryStoreTransaction(RepositorySession):
    def __init__(self, store: InMemoryRepositoryStore) -> None:
        self._store = store
        self._initial_types: set[type[BaseModel]] | None = None
        self._snapshots: dict[type[BaseModel], dict[str, dict[str, _Record[BaseModel]]]] | None = (
            None
        )

    def __enter__(self) -> "_MemoryStoreTransaction":
        self._store._lock.acquire()
        self._initial_types = set(self._store._repositories)
        self._snapshots = {
            entity_type: deepcopy(repository._records)
            for entity_type, repository in self._store._repositories.items()
        }
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None and self._snapshots is not None:
                for entity_type, snapshot in self._snapshots.items():
                    self._store._repositories[entity_type]._records = snapshot
                if self._initial_types is not None:
                    for entity_type in set(self._store._repositories) - self._initial_types:
                        del self._store._repositories[entity_type]
        finally:
            self._store._lock.release()

    def repository(self, entity_type: type[EntityT]) -> InMemoryRepository[EntityT]:
        return self._store.repository(entity_type)
