"""Durable, bounded conversational references that are always revalidated."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.conversation import EntityKind, EntityResolution, EntityResolutionStatus
from app.domain.models import ConversationEntityReference, ConversationMemory
from app.repositories.interfaces import RepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver


class ConversationMemoryService:
    def __init__(self, store: RepositoryStore, resolver: ConversationEntityResolver) -> None:
        self._store = store
        self._resolver = resolver

    def load(self, access: ProjectAccessContext) -> ConversationMemory:
        ensure_permission(access, ProjectPermission.READ)
        memory = self._store.repository(ConversationMemory).get(
            access.project_id, _memory_id(access)
        )
        return memory or ConversationMemory(
            id=_memory_id(access), project_id=access.project_id, actor_id=access.actor.user_id
        )

    def remember_reference(
        self,
        access: ProjectAccessContext,
        kind: EntityKind,
        entity_id: str,
        *,
        topic: str | None = None,
    ) -> ConversationMemory:
        resolution = self._resolver.resolve(access, kind, entity_id)
        if resolution.status is not EntityResolutionStatus.RESOLVED or resolution.entity_id is None:
            raise ValueError("only a current project entity can be remembered")
        repository = self._store.repository(ConversationMemory)
        current = self.load(access)
        refs = [
            item
            for item in current.recent_entities
            if not (item.kind == kind.value and item.entity_id == resolution.entity_id)
        ]
        refs.insert(0, ConversationEntityReference(kind=kind.value, entity_id=resolution.entity_id))
        saved = current.model_copy(
            update={
                "recent_entities": refs[:8],
                "recent_topic": topic,
                "updated_at": datetime.now(UTC),
            }
        )
        if repository.get(access.project_id, current.id) is None:
            return repository.create(saved)
        return repository.save(saved, expected_version=current.version)

    def resolve_recent(self, access: ProjectAccessContext, kind: EntityKind) -> EntityResolution:
        reference = next(
            (item for item in self.load(access).recent_entities if item.kind == kind.value), None
        )
        if reference is None:
            return EntityResolution(
                kind=kind, reference="recent context", status=EntityResolutionStatus.NOT_FOUND
            )
        return self._resolver.resolve(access, kind, reference.entity_id)

    def remember_pending(
        self,
        access: ProjectAccessContext,
        *,
        clarification: str | None = None,
        confirmation: str | None = None,
        proposed_action: str | None = None,
    ) -> ConversationMemory:
        repository = self._store.repository(ConversationMemory)
        current = self.load(access)
        if (
            current.pending_clarification == clarification
            and current.pending_confirmation == confirmation
            and current.recent_proposed_action == proposed_action
        ):
            return current
        saved = current.model_copy(
            update={
                "pending_clarification": clarification,
                "pending_confirmation": confirmation,
                "recent_proposed_action": proposed_action,
                "updated_at": datetime.now(UTC),
            }
        )
        if repository.get(access.project_id, current.id) is None:
            return repository.create(saved)
        return repository.save(saved, expected_version=current.version)


def _memory_id(access: ProjectAccessContext) -> str:
    digest = sha256(f"{access.project_id}\x00{access.actor.user_id}".encode()).hexdigest()[:24]
    return f"mem_{digest}"


__all__ = ["ConversationMemoryService"]
