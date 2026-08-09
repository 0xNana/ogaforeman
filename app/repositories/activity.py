"""Persistence helpers for the append-only activity timeline."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from hashlib import sha256
from typing import TypeVar

from app.domain.activity import ActivitySpec, MutationContext, activity_id, mutation_fingerprint
from app.domain.models import ActivityEvent
from app.repositories.interfaces import RepositorySession, RepositoryStore


ResultT = TypeVar("ResultT")


class ActivityIdempotencyConflict(RuntimeError):
    """An idempotency key was reused for a different mutation envelope."""

    code = "DUPLICATE_IDEMPOTENCY_KEY"


class ActivityRepository:
    """Typed transaction boundary for activity writes.

    The repository intentionally exposes the shared session callback so callers
    can couple a domain write and its activity in one Firestore transaction.
    """

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, project_id: str, entity_id: str) -> ActivityEvent | None:
        return self._store.repository(ActivityEvent).get(project_id, entity_id)

    def list(self, project_id: str) -> Sequence[ActivityEvent]:
        return self._store.repository(ActivityEvent).list(project_id)

    def run_transaction(self, operation: Callable[[RepositorySession], ResultT]) -> ResultT:
        return self._store.run_transaction(operation)

    @staticmethod
    def build_event(context: MutationContext, spec: ActivitySpec) -> ActivityEvent:
        fingerprint = mutation_fingerprint(context, spec)
        metadata = dict(spec.metadata)
        # Store only a one-way digest and a bounded, non-sensitive replay marker.
        metadata["_mutation_fingerprint"] = fingerprint
        metadata["_idempotency_key_digest"] = sha256(
            context.idempotency_key.encode("utf-8")
        ).hexdigest()[:16]
        return ActivityEvent(
            id=activity_id(context),
            project_id=context.project_id,
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            action=spec.action,
            entity_type=spec.entity_type,
            entity_id=spec.entity_id,
            summary=spec.summary,
            metadata=metadata,
            source_event_id=context.source_event_id,
            agent_run_id=context.agent_run_id,
            created_at=context.occurred_at,
        )

    @staticmethod
    def ensure_replay_matches(existing: ActivityEvent, expected: ActivityEvent) -> None:
        if (
            existing.project_id != expected.project_id
            or existing.action != expected.action
            or existing.entity_type != expected.entity_type
            or existing.entity_id != expected.entity_id
            or existing.metadata.get("_mutation_fingerprint")
            != expected.metadata.get("_mutation_fingerprint")
        ):
            raise ActivityIdempotencyConflict(
                "idempotency key already identifies a different mutation"
            )


__all__ = ["ActivityIdempotencyConflict", "ActivityRepository"]
