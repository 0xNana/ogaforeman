from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from threading import Barrier
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.repositories.memory import InMemoryRepositoryStore
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.event_claims import (
    ClaimOutcome,
    EventClaimConflict,
    EventClaimService,
    InvalidEventClaim,
)


NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


def make_event(**updates: object) -> ProjectEvent:
    values: dict[str, object] = {
        "event_id": "evt_update001",
        "project_id": "prj_ridge",
        "event_type": EventType.SITE_UPDATE_RECEIVED,
        "source": EventSource.WEB,
        "occurred_at": NOW,
        "received_at": NOW,
        "actor": EventActor(type=EventActorType.USER, id="usr_foreman"),
        "idempotency_key": "site-update:sup_update001:v1",
        "correlation_id": "req_update001",
        "payload": {
            "site_update_id": "sup_update001",
            "text": "Blockwork is complete.",
            "transcript": None,
            "attachment_ids": [],
        },
        "metadata": {},
    }
    values.update(updates)
    return ProjectEvent(**values)


def test_duplicate_completion_returns_prior_result_without_reclaiming() -> None:
    service = EventClaimService(InMemoryRepositoryStore(), lease_seconds=30)
    event = make_event()

    first = service.claim(event, now=NOW)
    assert first.claim_token is not None
    service.complete(
        event,
        claim_token=first.claim_token,
        result_ref="run_update001",
        now=NOW + timedelta(seconds=1),
    )
    replay = service.claim(event, now=NOW + timedelta(seconds=2))

    assert first.outcome is ClaimOutcome.ACQUIRED
    assert replay.outcome is ClaimOutcome.DUPLICATE_COMPLETED
    assert replay.result_ref == "run_update001"


def test_concurrent_delivery_has_one_claim_and_one_busy_result() -> None:
    service = EventClaimService(InMemoryRepositoryStore(), lease_seconds=30)
    event = make_event()
    barrier = Barrier(2)

    def claim(_delivery: int):
        barrier.wait()
        return service.claim(event, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, [1, 2]))

    assert sorted(result.outcome for result in results) == [
        ClaimOutcome.ACQUIRED,
        ClaimOutcome.BUSY,
    ]
    busy = next(result for result in results if result.outcome is ClaimOutcome.BUSY)
    assert busy.claim_token is None


def test_expired_lease_is_reclaimed_with_new_token_and_attempt() -> None:
    service = EventClaimService(InMemoryRepositoryStore(), lease_seconds=30)
    event = make_event()
    first = service.claim(event, now=NOW)
    assert first.claim_token is not None

    reclaimed = service.claim(event, now=NOW + timedelta(seconds=31))

    assert reclaimed.outcome is ClaimOutcome.ACQUIRED
    assert reclaimed.attempts == 2
    assert reclaimed.claim_token is not None
    assert reclaimed.claim_token != first.claim_token

    with pytest.raises(InvalidEventClaim, match="token"):
        service.complete(
            event,
            claim_token=first.claim_token,
            result_ref="run_stale",
            now=NOW + timedelta(seconds=32),
        )


def test_same_idempotency_key_with_different_payload_conflicts() -> None:
    service = EventClaimService(InMemoryRepositoryStore())
    service.claim(make_event(), now=NOW)

    with pytest.raises(EventClaimConflict, match="fingerprint"):
        service.claim(
            make_event(
                payload={
                    "site_update_id": "sup_update001",
                    "text": "Different payload",
                    "transcript": None,
                    "attachment_ids": [],
                }
            ),
            now=NOW,
        )


def test_failures_become_dead_lettered_at_attempt_limit() -> None:
    service = EventClaimService(InMemoryRepositoryStore(), lease_seconds=30, max_attempts=2)
    event = make_event()

    first = service.claim(event, now=NOW)
    assert first.claim_token is not None
    failed = service.fail(
        event,
        claim_token=first.claim_token,
        error_code="TEMP",
        error_summary="retry",
        now=NOW + timedelta(seconds=1),
    )
    assert failed.status.value == "failed"

    second = service.claim(event, now=NOW + timedelta(seconds=2))
    assert second.claim_token is not None
    dead = service.fail(
        event,
        claim_token=second.claim_token,
        error_code="PERM",
        error_summary="no retry",
        now=NOW + timedelta(seconds=3),
    )
    assert dead.status.value == "dead_lettered"
    assert dead.dead_lettered_at == NOW + timedelta(seconds=3)
    assert dead.dead_letter_reason == "PERM: no retry"


def test_repeated_abandoned_leases_are_bounded_and_dead_lettered() -> None:
    service = EventClaimService(InMemoryRepositoryStore(), lease_seconds=10, max_attempts=2)
    event = make_event()

    service.claim(event, now=NOW)
    reclaimed = service.claim(event, now=NOW + timedelta(seconds=11))
    terminal = service.claim(event, now=NOW + timedelta(seconds=22))

    assert reclaimed.outcome is ClaimOutcome.ACQUIRED
    assert reclaimed.attempts == 2
    assert terminal.outcome is ClaimOutcome.DEAD_LETTERED
    assert terminal.claim_token is None
    assert terminal.dead_letter_reason == "CLAIM_ATTEMPTS_EXHAUSTED: claim lease expired"


@pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for Firestore claim integration",
)
def test_firestore_concurrent_delivery_creates_one_active_claim() -> None:
    client = firestore.Client(project=f"oga-foreman-test-{uuid4().hex}")
    service = EventClaimService(FirestoreRepositoryStore(client), lease_seconds=30)
    event = make_event()
    barrier = Barrier(2)

    def claim(_delivery: int):
        barrier.wait()
        return service.claim(event, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, [1, 2]))

    assert sorted(result.outcome for result in results) == [
        ClaimOutcome.ACQUIRED,
        ClaimOutcome.BUSY,
    ]
