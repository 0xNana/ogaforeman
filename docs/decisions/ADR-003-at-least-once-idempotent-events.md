# ADR-003: Assume At-Least-Once Events and Make Processing Idempotent

## Status

Accepted

## Context

Pub/Sub and external event sources can redeliver messages. A construction workflow must not create duplicate requests, blockers, notifications, or purchases because a worker retried.

## Decision

Every event has a stable event ID and idempotency key. Workers claim events transactionally in Firestore, workflow steps persist checkpoints, domain mutations use deterministic fingerprints/version checks, and external actions use an outbox/claim record.

## Consequences

- Every mutation API and tool needs idempotency tests.
- Event payloads are immutable; corrections are new events.
- Operations can replay events safely after fixing a projection or transient failure.
