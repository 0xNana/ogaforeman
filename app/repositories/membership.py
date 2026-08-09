from __future__ import annotations

from collections.abc import Sequence
from typing import Callable, Generic, Protocol, TypeVar

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel

from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectPermission,
    authorize_project_member,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.models import ProjectMember, User

from .interfaces import ProjectRepository, RepositoryError, RepositoryTransaction


EntityT = TypeVar("EntityT", bound=BaseModel)
ResultT = TypeVar("ResultT")


class IdentityRepository(Protocol):
    def get_by_subject(self, subject: str) -> User | None:
        """Resolve one verified external subject to a canonical application user."""

    def provision(self, user: User) -> User:
        """Create or return the canonical user for one verified subject."""


class InMemoryIdentityRepository(IdentityRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, user: User) -> None:
        if user.identity_subject in self._users:
            raise RepositoryError("identity subject is already mapped to a user")
        self._users[user.identity_subject] = user.model_copy(deep=True)

    def get_by_subject(self, subject: str) -> User | None:
        user = self._users.get(subject)
        return user.model_copy(deep=True) if user else None

    def provision(self, user: User) -> User:
        existing = self._users.get(user.identity_subject)
        if existing is not None:
            return existing.model_copy(deep=True)
        self._users[user.identity_subject] = user.model_copy(deep=True)
        return user.model_copy(deep=True)


class FirestoreIdentityRepository(IdentityRepository):
    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def get_by_subject(self, subject: str) -> User | None:
        snapshots = list(
            self._client.collection("users")
            .where(filter=FieldFilter("identity_subject", "==", subject))
            .limit(2)
            .stream()
        )
        if len(snapshots) > 1:
            raise RepositoryError("identity subject maps to more than one user")
        if not snapshots:
            return None
        data = snapshots[0].to_dict() or {}
        data.pop("_repository_version", None)
        return User.model_validate(data)

    def provision(self, user: User) -> User:
        reference = self._client.collection("users").document(user.id)
        try:
            reference.create(user.model_dump(mode="python"))
            return user
        except AlreadyExists:
            snapshot = reference.get()
            if not snapshot.exists:
                raise RepositoryError("concurrent identity provisioning did not converge") from None
            data = snapshot.to_dict() or {}
            data.pop("_repository_version", None)
            existing = User.model_validate(data)
            if existing.identity_subject != user.identity_subject:
                raise RepositoryError("canonical user ID is mapped to another identity")
            return existing


class MembershipRepository:
    def __init__(self, repository: ProjectRepository[ProjectMember]) -> None:
        self._repository = repository

    def add(self, membership: ProjectMember) -> ProjectMember:
        return self._repository.create(membership)

    def get(self, project_id: str, user_id: str) -> ProjectMember | None:
        return self._repository.get(project_id, user_id)

    def require_access(
        self,
        actor: AuthenticatedUser,
        project_id: str,
        permission: ProjectPermission,
    ) -> ProjectAccessContext:
        return authorize_project_member(
            actor,
            project_id,
            self.get(project_id, actor.user_id),
            permission,
        )


class AuthorizedProjectRepository(Generic[EntityT], ProjectRepository[EntityT]):
    def __init__(
        self,
        repository: ProjectRepository[EntityT],
        access: ProjectAccessContext,
        *,
        mutation_permission: ProjectPermission = ProjectPermission.OPERATE,
    ) -> None:
        self._repository = repository
        self._access = access
        self._mutation_permission = mutation_permission

    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        self._authorize_read(project_id)
        return self._repository.get(project_id, entity_id)

    def require(self, project_id: str, entity_id: str) -> EntityT:
        self._authorize_read(project_id)
        return self._repository.require(project_id, entity_id)

    def list(self, project_id: str) -> Sequence[EntityT]:
        self._authorize_read(project_id)
        return self._repository.list(project_id)

    def create(self, entity: EntityT) -> EntityT:
        self._authorize_mutation(_project_id(entity))
        return self._repository.create(entity)

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        self._authorize_mutation(_project_id(entity))
        return self._repository.save(entity, expected_version=expected_version)

    def delete(
        self,
        project_id: str,
        entity_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        self._authorize_mutation(project_id)
        self._repository.delete(project_id, entity_id, expected_version=expected_version)

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        self._authorize_read(project_id)
        return self._repository.version_of(project_id, entity_id)

    def run_transaction(
        self,
        operation: Callable[[RepositoryTransaction[EntityT]], ResultT],
    ) -> ResultT:
        def authorize_transaction(transaction: RepositoryTransaction[EntityT]) -> ResultT:
            return operation(
                _AuthorizedTransaction(
                    transaction,
                    self._access,
                    self._mutation_permission,
                )
            )

        return self._repository.run_transaction(authorize_transaction)

    def _authorize_read(self, project_id: str) -> None:
        ensure_project_scope(self._access, project_id)
        ensure_permission(self._access, ProjectPermission.READ)

    def _authorize_mutation(self, project_id: str) -> None:
        ensure_project_scope(self._access, project_id)
        ensure_permission(self._access, self._mutation_permission)


class _AuthorizedTransaction(Generic[EntityT], RepositoryTransaction[EntityT]):
    def __init__(
        self,
        transaction: RepositoryTransaction[EntityT],
        access: ProjectAccessContext,
        mutation_permission: ProjectPermission,
    ) -> None:
        self._transaction = transaction
        self._access = access
        self._mutation_permission = mutation_permission

    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        self._authorize_read(project_id)
        return self._transaction.get(project_id, entity_id)

    def require(self, project_id: str, entity_id: str) -> EntityT:
        self._authorize_read(project_id)
        return self._transaction.require(project_id, entity_id)

    def list(self, project_id: str) -> Sequence[EntityT]:
        self._authorize_read(project_id)
        return self._transaction.list(project_id)

    def create(self, entity: EntityT) -> EntityT:
        self._authorize_mutation(_project_id(entity))
        return self._transaction.create(entity)

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        self._authorize_mutation(_project_id(entity))
        return self._transaction.save(entity, expected_version=expected_version)

    def delete(
        self,
        project_id: str,
        entity_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        self._authorize_mutation(project_id)
        self._transaction.delete(project_id, entity_id, expected_version=expected_version)

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        self._authorize_read(project_id)
        return self._transaction.version_of(project_id, entity_id)

    def _authorize_read(self, project_id: str) -> None:
        ensure_project_scope(self._access, project_id)
        ensure_permission(self._access, ProjectPermission.READ)

    def _authorize_mutation(self, project_id: str) -> None:
        ensure_project_scope(self._access, project_id)
        ensure_permission(self._access, self._mutation_permission)


def _project_id(entity: BaseModel) -> str:
    project_id = getattr(entity, "project_id", None)
    if not isinstance(project_id, str):
        raise TypeError("authorized repository entities must expose project_id")
    return project_id
