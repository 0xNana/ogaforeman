from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
import json
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.transaction import Transaction
from pydantic import BaseModel

from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Attachment,
    ConversationMemory,
    ConversationProposalClaim,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    ProcessedEvent,
    Project,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.domain.materials import MaterialLedgerEntry
from app.domain.import_records import (
    ImportProvenance,
    MaterialRequirement,
    ProjectImportRecord,
    ProjectPhase,
    ProjectSource,
)
from app.infrastructure.firestore import decode_firestore_value, encode_firestore_value

from .interfaces import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    ProjectRepository,
    RepositoryError,
    RepositorySession,
    RepositoryStore,
    RepositoryTransaction,
    VersionConflictError,
)


EntityT = TypeVar("EntityT", bound=BaseModel)
ResultT = TypeVar("ResultT")
ReadVersionKey = tuple[type[BaseModel], str, str]

_COLLECTIONS: dict[type[BaseModel], str] = {
    Project: "projects",
    ProjectMember: "members",
    Task: "tasks",
    SiteUpdate: "site_updates",
    Attachment: "attachments",
    Issue: "issues",
    Material: "materials",
    MaterialLedgerEntry: "material_ledger",
    MaterialRequest: "material_requests",
    Approval: "approvals",
    DailyReport: "daily_reports",
    AgentRun: "agent_runs",
    ActivityEvent: "activity",
    ProcessedEvent: "processed_events",
    OutboxMessage: "outbox",
    ConversationMemory: "conversation_memory",
    ConversationProposalClaim: "conversation_proposal_claims",
    ProjectImportRecord: "project_imports",
    ProjectSource: "project_sources",
    ProjectPhase: "project_phases",
    MaterialRequirement: "material_requirements",
    ImportProvenance: "import_provenance",
}
_REPOSITORY_VERSION_FIELD = "_repository_version"


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def firestore_collection_name(entity_type: type[BaseModel]) -> str:
    """Return the documented Firestore collection for a domain entity type."""

    try:
        return _COLLECTIONS[entity_type]
    except KeyError as exc:
        raise TypeError(f"no Firestore collection mapping for {entity_type.__name__}") from exc


def firestore_entity_id(entity: BaseModel) -> str:
    """Return the canonical Firestore document ID for a project-owned entity."""

    if isinstance(entity, ProjectMember):
        return entity.user_id
    entity_id = getattr(entity, "id", None)
    if not isinstance(entity_id, str):
        raise TypeError("repository entities must expose a canonical document ID")
    return entity_id


def firestore_document_data(entity: EntityT, *, version: int = 0) -> dict[str, Any]:
    """Serialize a validated entity for a Firestore document write."""

    if version < 0:
        raise ValueError("repository version cannot be negative")
    payload = encode_firestore_value(entity.model_dump(mode="python"))
    if not isinstance(entity, Project):
        payload[_REPOSITORY_VERSION_FIELD] = version
    return payload


class FirestoreRepository(Generic[EntityT], ProjectRepository[EntityT]):
    """Firestore-backed project repository for one typed project-owned entity.

    The client library transaction and transactional callback patterns follow the
    official Python samples and reference:
    https://cloud.google.com/firestore/docs/manage-data/transactions and
    https://cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.client.Client
    """

    def __init__(
        self,
        client: firestore.Client,
        entity_type: type[EntityT],
        *,
        transaction: Transaction | None = None,
        read_versions: dict[ReadVersionKey, int] | None = None,
    ) -> None:
        self._client = client
        self._entity_type = entity_type
        self._collection_name = firestore_collection_name(entity_type)
        self._transaction = transaction
        self._read_versions = read_versions if transaction is not None else None
        if transaction is not None and self._read_versions is None:
            self._read_versions = {}

    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        snapshot = self._document(project_id, entity_id).get(transaction=self._transaction)
        if not snapshot.exists:
            return None
        if self._read_versions is not None:
            self._read_versions[self._version_key(project_id, entity_id)] = self._snapshot_version(
                snapshot
            )
        return self._decode_snapshot(snapshot)

    def require(self, project_id: str, entity_id: str) -> EntityT:
        entity = self.get(project_id, entity_id)
        if entity is None:
            raise EntityNotFoundError(f"entity {entity_id} was not found in project {project_id}")
        return entity

    def list(self, project_id: str) -> Sequence[EntityT]:
        if self._entity_type is Project:
            project = self.get(project_id, project_id)
            return () if project is None else (project,)
        snapshots = self._collection(project_id).stream(transaction=self._transaction)
        entities = []
        for snapshot in snapshots:
            if self._read_versions is not None:
                self._read_versions[self._version_key(project_id, snapshot.id)] = (
                    self._snapshot_version(snapshot)
                )
            entities.append(self._decode_snapshot(snapshot))
        return tuple(sorted(entities, key=firestore_entity_id))

    def create(self, entity: EntityT) -> EntityT:
        if self._entity_type is Project:
            raise RepositoryError("projects must be created through the project service")
        project_id, entity_id = self._identity(entity)
        validated = self._validate_for_create(entity)
        reference = self._document(project_id, entity_id)
        payload = self._payload(validated, version=0)
        try:
            if self._transaction is None:
                reference.create(payload)
            else:
                self._transaction.create(reference, payload)
                if self._read_versions is not None:
                    self._read_versions[self._version_key(project_id, entity_id)] = 0
        except AlreadyExists as exc:
            raise EntityAlreadyExistsError(
                f"entity {entity_id} already exists in project {project_id}"
            ) from exc
        return validated

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        if self._transaction is not None:
            return self._save_in_transaction(self._transaction, entity, expected_version)

        transaction = self._client.transaction()

        @firestore.transactional
        def save_in_transaction(active_transaction: Transaction) -> EntityT:
            repository = FirestoreRepository(
                self._client,
                self._entity_type,
                transaction=active_transaction,
            )
            return repository._save_in_transaction(active_transaction, entity, expected_version)

        return save_in_transaction(transaction)

    def delete(
        self,
        project_id: str,
        entity_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        if self._transaction is not None:
            self._delete_in_transaction(self._transaction, project_id, entity_id, expected_version)
            return

        transaction = self._client.transaction()

        @firestore.transactional
        def delete_in_transaction(active_transaction: Transaction) -> None:
            repository = FirestoreRepository(
                self._client,
                self._entity_type,
                transaction=active_transaction,
            )
            repository._delete_in_transaction(
                active_transaction,
                project_id,
                entity_id,
                expected_version,
            )

        delete_in_transaction(transaction)

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        cache_key = self._version_key(project_id, entity_id)
        cached = self._read_versions.get(cache_key) if self._read_versions is not None else None
        if cached is not None:
            return cached
        snapshot = self._document(project_id, entity_id).get(transaction=self._transaction)
        if not snapshot.exists:
            return None
        version = self._snapshot_version(snapshot)
        if self._read_versions is not None:
            self._read_versions[cache_key] = version
        return version

    def run_transaction(
        self,
        operation: Callable[[RepositoryTransaction[EntityT]], ResultT],
    ) -> ResultT:
        if self._transaction is not None:
            return operation(self)

        transaction = self._client.transaction()

        @firestore.transactional
        def run_in_transaction(active_transaction: Transaction) -> ResultT:
            repository = FirestoreRepository(
                self._client,
                self._entity_type,
                transaction=active_transaction,
            )
            return operation(repository)

        try:
            return run_in_transaction(transaction)
        except AlreadyExists as exc:
            raise EntityAlreadyExistsError("an entity already exists in the transaction") from exc

    def _save_in_transaction(
        self,
        transaction: Transaction,
        entity: EntityT,
        expected_version: int | None,
    ) -> EntityT:
        project_id, entity_id = self._identity(entity)
        reference = self._document(project_id, entity_id)
        cache_key = self._version_key(project_id, entity_id)
        current_version = (
            self._read_versions.get(cache_key) if self._read_versions is not None else None
        )
        if current_version is None:
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                raise EntityNotFoundError(
                    f"entity {entity_id} was not found in project {project_id}"
                )
            current_version = self._snapshot_version(snapshot)
            if self._read_versions is not None:
                self._read_versions[cache_key] = current_version
        self._require_expected_version(expected_version, current_version)
        next_version = current_version + 1
        validated = self._validate_with_version(entity, next_version)
        transaction.set(reference, self._payload(validated, version=next_version))
        if self._read_versions is not None:
            self._read_versions[cache_key] = next_version
        return validated

    def _delete_in_transaction(
        self,
        transaction: Transaction,
        project_id: str,
        entity_id: str,
        expected_version: int | None,
    ) -> None:
        reference = self._document(project_id, entity_id)
        cache_key = self._version_key(project_id, entity_id)
        current_version = (
            self._read_versions.get(cache_key) if self._read_versions is not None else None
        )
        if current_version is None:
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                raise EntityNotFoundError(
                    f"entity {entity_id} was not found in project {project_id}"
                )
            current_version = self._snapshot_version(snapshot)
            if self._read_versions is not None:
                self._read_versions[cache_key] = current_version
        self._require_expected_version(expected_version, current_version)
        transaction.delete(reference)
        if self._read_versions is not None:
            self._read_versions.pop(cache_key, None)

    def _collection(self, project_id: str):
        if self._entity_type is Project:
            return self._client.collection("projects")
        return (
            self._client.collection("projects")
            .document(project_id)
            .collection(self._collection_name)
        )

    def _document(self, project_id: str, entity_id: str):
        if self._entity_type is Project:
            if entity_id != project_id:
                raise EntityNotFoundError(
                    f"entity {entity_id} was not found in project {project_id}"
                )
            return self._client.collection("projects").document(project_id)
        return self._collection(project_id).document(entity_id)

    def _version_key(self, project_id: str, entity_id: str) -> ReadVersionKey:
        return (self._entity_type, project_id, entity_id)

    def _decode_snapshot(self, snapshot) -> EntityT:
        data = decode_firestore_value(snapshot.to_dict() or {})
        repository_version = data.pop(_REPOSITORY_VERSION_FIELD, 0)
        if "version" in self._entity_type.model_fields:
            data["version"] = repository_version
        if self._entity_type is ProjectImportRecord:
            # Draft contracts are strict at the model boundary. Firestore
            # stores enum/date/decimal values in their JSON-compatible form,
            # so validate the durable record through Pydantic's JSON parser on
            # reload rather than weakening extraction-time strictness.
            return self._entity_type.model_validate_json(json.dumps(data, default=_json_default))
        return self._entity_type.model_validate(data)

    @staticmethod
    def _snapshot_version(snapshot) -> int:
        data = snapshot.to_dict() or {}
        version = data.get(_REPOSITORY_VERSION_FIELD, 0)
        if not isinstance(version, int) or version < 0:
            raise RepositoryError("stored repository version is invalid")
        return version

    @staticmethod
    def _identity(entity: EntityT) -> tuple[str, str]:
        if isinstance(entity, Project):
            return entity.id, entity.id
        project_id = getattr(entity, "project_id", None)
        if not isinstance(project_id, str):
            raise TypeError("repository entities must expose a string project_id field")
        return project_id, firestore_entity_id(entity)

    def _validate_for_create(self, entity: EntityT) -> EntityT:
        validated = self._entity_type.model_validate(entity.model_dump())
        if "version" in self._entity_type.model_fields and getattr(validated, "version") != 0:
            raise VersionConflictError("new repository entities must start at version 0")
        return validated

    def _validate_with_version(self, entity: EntityT, version: int) -> EntityT:
        data = entity.model_dump()
        if "version" in self._entity_type.model_fields:
            data["version"] = version
        return self._entity_type.model_validate(data)

    def _payload(self, entity: EntityT, *, version: int) -> dict[str, Any]:
        return firestore_document_data(entity, version=version)

    @staticmethod
    def _require_expected_version(expected_version: int | None, current_version: int) -> None:
        if expected_version is None:
            raise VersionConflictError("expected_version is required for updates and deletes")
        if expected_version != current_version:
            raise VersionConflictError(
                f"expected_version {expected_version} does not match current version {current_version}"
            )


class FirestoreRepositoryStore(RepositoryStore):
    """Shares one Firestore transaction across typed project repositories."""

    def __init__(
        self,
        client: firestore.Client,
        *,
        transaction: Transaction | None = None,
    ) -> None:
        self._client = client
        self._transaction = transaction
        self._read_versions: dict[ReadVersionKey, int] | None = (
            {} if transaction is not None else None
        )

    def repository(self, entity_type: type[EntityT]) -> FirestoreRepository[EntityT]:
        return FirestoreRepository(
            self._client,
            entity_type,
            transaction=self._transaction,
            read_versions=self._read_versions,
        )

    def run_transaction(self, operation: Callable[[RepositorySession], ResultT]) -> ResultT:
        if self._transaction is not None:
            return operation(self)

        transaction = self._client.transaction()

        @firestore.transactional
        def run_in_transaction(active_transaction: Transaction) -> ResultT:
            session = FirestoreRepositoryStore(
                self._client,
                transaction=active_transaction,
            )
            return operation(session)

        try:
            return run_in_transaction(transaction)
        except AlreadyExists as exc:
            raise EntityAlreadyExistsError("an entity already exists in the transaction") from exc
