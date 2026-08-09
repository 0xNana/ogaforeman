from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.domain.events import ProjectEvent
from app.domain.models import ProcessedEvent
from app.domain.enums import ProcessedEventStatus
from app.repositories.event_claims import EventClaimRepository
from app.repositories.interfaces import (
    EntityNotFoundError,
    ProjectRepository,
    RepositoryStore,
)


class EventClaimConflict(RuntimeError):
    """The idempotency key was reused for a different event payload."""


class InvalidEventClaim(RuntimeError):
    """A completion or failure was attempted by a stale or unknown claim owner."""


class ClaimOutcome(StrEnum):
    ACQUIRED = "acquired"
    DUPLICATE_COMPLETED = "duplicate_completed"
    BUSY = "busy"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True, slots=True)
class EventClaimResult:
    outcome: ClaimOutcome
    event_id: str
    attempts: int
    claim_token: str | None = None
    lease_expires_at: datetime | None = None
    result_ref: str | None = None
    dead_letter_reason: str | None = None


class EventClaimService:
    """Atomically claim and finalize at-least-once project events."""

    def __init__(
        self,
        store: RepositoryStore,
        *,
        lease_seconds: int = 60,
        max_attempts: int = 3,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self._repository = EventClaimRepository(store)
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts

    def claim(
        self,
        event: ProjectEvent,
        *,
        now: datetime | None = None,
    ) -> EventClaimResult:
        if now is not None:
            _aware_now(now)
        token = secrets.token_urlsafe(24)

        def operation(repository: ProjectRepository[ProcessedEvent]) -> EventClaimResult:
            current_time = _aware_now(now)
            existing = repository.get(event.project_id, event.idempotency_key)
            if existing is None:
                created = repository.create(
                    ProcessedEvent(
                        id=event.idempotency_key,
                        project_id=event.project_id,
                        event_id=event.event_id,
                        schema_version=event.schema_version,
                        event_type=event.event_type.value,
                        event_fingerprint=event.fingerprint,
                        status=ProcessedEventStatus.CLAIMED,
                        claim_token=token,
                        lease_expires_at=current_time + timedelta(seconds=self._lease_seconds),
                        first_seen_at=current_time,
                    )
                )
                return _claim_result(ClaimOutcome.ACQUIRED, created, expose_token=True)

            self._ensure_same_event(existing, event)
            if existing.status is ProcessedEventStatus.COMPLETED:
                return _claim_result(ClaimOutcome.DUPLICATE_COMPLETED, existing)
            if existing.status is ProcessedEventStatus.DEAD_LETTERED:
                return _claim_result(ClaimOutcome.DEAD_LETTERED, existing)
            if (
                existing.status is ProcessedEventStatus.CLAIMED
                and existing.lease_expires_at is not None
                and existing.lease_expires_at > current_time
            ):
                return _claim_result(ClaimOutcome.BUSY, existing)
            if existing.attempts >= self._max_attempts:
                error_code = existing.last_error_code or "CLAIM_ATTEMPTS_EXHAUSTED"
                error_summary = existing.last_error_summary or "claim lease expired"
                dead_lettered = existing.model_copy(
                    update={
                        "status": ProcessedEventStatus.DEAD_LETTERED,
                        "claim_token": None,
                        "lease_expires_at": None,
                        "last_error_code": error_code,
                        "last_error_summary": error_summary,
                        "dead_lettered_at": current_time,
                        "dead_letter_reason": f"{error_code}: {error_summary}",
                    }
                )
                saved = repository.save(dead_lettered, expected_version=existing.version)
                return _claim_result(ClaimOutcome.DEAD_LETTERED, saved)

            reclaimed = existing.model_copy(
                update={
                    "status": ProcessedEventStatus.CLAIMED,
                    "claim_token": token,
                    "lease_expires_at": current_time + timedelta(seconds=self._lease_seconds),
                    "attempts": existing.attempts + 1,
                    "dead_lettered_at": None,
                    "dead_letter_reason": None,
                }
            )
            return _claim_result(
                ClaimOutcome.ACQUIRED,
                repository.save(reclaimed, expected_version=existing.version),
                expose_token=True,
            )

        return self._repository.run_transaction(operation)

    def complete(
        self,
        event: ProjectEvent,
        *,
        claim_token: str,
        result_ref: str,
        now: datetime | None = None,
    ) -> ProcessedEvent:
        if now is not None:
            _aware_now(now)
        if not result_ref or len(result_ref) > 1_000:
            raise ValueError("result_ref must contain between 1 and 1000 characters")

        def operation(repository: ProjectRepository[ProcessedEvent]) -> ProcessedEvent:
            current_time = _aware_now(now)
            existing = self._require_event(repository, event)
            self._require_active_claim(existing, claim_token, current_time)
            completed = existing.model_copy(
                update={
                    "status": ProcessedEventStatus.COMPLETED,
                    "result_ref": result_ref,
                    "completed_at": current_time,
                    "claim_token": None,
                    "lease_expires_at": None,
                    "last_error_code": None,
                    "last_error_summary": None,
                }
            )
            return repository.save(completed, expected_version=existing.version)

        return self._repository.run_transaction(operation)

    def fail(
        self,
        event: ProjectEvent,
        *,
        claim_token: str,
        error_code: str,
        error_summary: str,
        terminal: bool = False,
        now: datetime | None = None,
    ) -> ProcessedEvent:
        if now is not None:
            _aware_now(now)
        if not error_code or not error_summary:
            raise ValueError("error_code and error_summary are required")

        def operation(repository: ProjectRepository[ProcessedEvent]) -> ProcessedEvent:
            current_time = _aware_now(now)
            existing = self._require_event(repository, event)
            self._require_active_claim(existing, claim_token, current_time)
            should_dead_letter = terminal or existing.attempts >= self._max_attempts
            failed = existing.model_copy(
                update={
                    "status": (
                        ProcessedEventStatus.DEAD_LETTERED
                        if should_dead_letter
                        else ProcessedEventStatus.FAILED
                    ),
                    "claim_token": None,
                    "lease_expires_at": None,
                    "last_error_code": error_code,
                    "last_error_summary": error_summary,
                    "dead_lettered_at": current_time if should_dead_letter else None,
                    "dead_letter_reason": (
                        f"{error_code}: {error_summary}" if should_dead_letter else None
                    ),
                }
            )
            return repository.save(failed, expected_version=existing.version)

        return self._repository.run_transaction(operation)

    @staticmethod
    def _ensure_same_event(existing: ProcessedEvent, event: ProjectEvent) -> None:
        identity_matches = (
            existing.project_id == event.project_id
            and existing.event_id == event.event_id
            and existing.schema_version == event.schema_version
            and existing.event_type == event.event_type.value
        )
        if not identity_matches or existing.event_fingerprint != event.fingerprint:
            raise EventClaimConflict("idempotency key already has a different event fingerprint")

    def _require_event(
        self,
        repository: ProjectRepository[ProcessedEvent],
        event: ProjectEvent,
    ) -> ProcessedEvent:
        existing = repository.get(event.project_id, event.idempotency_key)
        if existing is None:
            raise EntityNotFoundError("event has not been claimed")
        self._ensure_same_event(existing, event)
        return existing

    @staticmethod
    def _require_active_claim(
        existing: ProcessedEvent,
        claim_token: str,
        now: datetime,
    ) -> None:
        if existing.status is not ProcessedEventStatus.CLAIMED:
            raise InvalidEventClaim(f"event is {existing.status.value}, not claimed")
        if existing.claim_token is None or not secrets.compare_digest(
            existing.claim_token,
            claim_token,
        ):
            raise InvalidEventClaim("claim token does not match")
        if existing.lease_expires_at is None or existing.lease_expires_at <= now:
            raise InvalidEventClaim("claim lease has expired")


def _aware_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return current


def _claim_result(
    outcome: ClaimOutcome,
    event: ProcessedEvent,
    *,
    expose_token: bool = False,
) -> EventClaimResult:
    return EventClaimResult(
        outcome=outcome,
        event_id=event.event_id,
        attempts=event.attempts,
        claim_token=event.claim_token if expose_token else None,
        lease_expires_at=event.lease_expires_at,
        result_ref=event.result_ref,
        dead_letter_reason=event.dead_letter_reason,
    )
