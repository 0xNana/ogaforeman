"""Atomic mutation plus audit service."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.domain.activity import (
    ActivitySpec,
    MutationContext,
    MutationContextRequiredError,
)
from app.domain.models import ActivityEvent, ConversationProposalClaim
from app.repositories.activity import ActivityIdempotencyConflict, ActivityRepository
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore


EntityT = TypeVar("EntityT")
AdditionalActivity = tuple[MutationContext, ActivitySpec]


@dataclass(frozen=True, slots=True)
class MutationResult(Generic[EntityT]):
    value: EntityT | None
    activity: ActivityEvent
    duplicate: bool = False

    @property
    def replayed(self) -> bool:
        return self.duplicate


class ActivityService:
    """Run one deterministic mutation and append exactly one activity atomically."""

    def __init__(self, store: RepositoryStore) -> None:
        self._activities = ActivityRepository(store)

    def mutate(
        self,
        context: MutationContext | None,
        spec: ActivitySpec,
        mutation: Callable[[RepositorySession], EntityT],
        *,
        replay: Callable[[RepositorySession, ActivityEvent], EntityT | None] | None = None,
        additional_activities: Sequence[AdditionalActivity] = (),
    ) -> MutationResult[EntityT]:
        if context is None:
            raise MutationContextRequiredError("mutation context is required")
        expected_activity = self._activities.build_event(context, spec)
        expected_additional = [
            self._activities.build_event(additional_context, additional_spec)
            for additional_context, additional_spec in additional_activities
        ]
        expected_ids = [expected_activity.id, *(item.id for item in expected_additional)]
        if len(expected_ids) != len(set(expected_ids)):
            raise ValueError("activity idempotency scopes must be distinct")
        if any(item.project_id != context.project_id for item in expected_additional):
            raise ValueError("additional activities must share the mutation project")

        def operation(session: RepositorySession) -> MutationResult[EntityT]:
            _validate_confirmation_fence(session, context)
            repository = session.repository(ActivityEvent)
            existing = repository.get(context.project_id, expected_activity.id)
            missing_additional = _missing_or_validate(repository, expected_additional)
            if existing is not None:
                self._activities.ensure_replay_matches(existing, expected_activity)
                value = replay(session, existing) if replay is not None else None
                _create_missing(repository, missing_additional)
                return MutationResult(value=value, activity=existing, duplicate=True)

            value = mutation(session)
            _ensure_result_scope(value, context.project_id, spec.entity_id)
            saved_activity = repository.create(expected_activity)
            _create_missing(repository, missing_additional)
            return MutationResult(value=value, activity=saved_activity, duplicate=False)

        return self._activities.run_transaction(operation)


def _validate_confirmation_fence(session: RepositorySession, context: MutationContext) -> None:
    if context.confirmation_claim_id is None:
        return
    claim = session.repository(ConversationProposalClaim).require(
        context.project_id, context.confirmation_claim_id
    )
    if (
        claim.outcome != "confirming"
        or claim.actor_id != context.actor_id
        or claim.confirmation_attempt_id != context.confirmation_attempt_id
        or claim.command_fingerprint != context.confirmation_command_fingerprint
    ):
        raise PermissionError("conversation confirmation attempt is no longer authorized")


def _missing_or_validate(
    repository: ProjectRepository[ActivityEvent],
    expected_events: Sequence[ActivityEvent],
) -> list[ActivityEvent]:
    missing: list[ActivityEvent] = []
    for expected in expected_events:
        existing = repository.get(expected.project_id, expected.id)
        if existing is None:
            missing.append(expected)
            continue
        ActivityRepository.ensure_replay_matches(existing, expected)
    return missing


def _create_missing(
    repository: ProjectRepository[ActivityEvent],
    expected_events: Sequence[ActivityEvent],
) -> None:
    for expected in expected_events:
        repository.create(expected)


def _ensure_result_scope(value: object, project_id: str, entity_id: str) -> None:
    if isinstance(value, BaseModel):
        actual_project = getattr(value, "project_id", project_id)
        actual_id = getattr(value, "id", entity_id)
        if actual_project != project_id or actual_id != entity_id:
            raise ValueError("mutation returned an entity outside the activity scope")


__all__ = [
    "ActivityIdempotencyConflict",
    "ActivityService",
    "AdditionalActivity",
    "MutationResult",
]
