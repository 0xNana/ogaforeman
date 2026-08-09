# ADR-002: Firestore Is the Project Source of Truth

## Status

Accepted

## Context

Project entities have relational references and need durable writes, activity audit, approval transitions, and restart-safe workflow state. The current process-local dictionary cannot provide those guarantees.

## Decision

Use Firestore Native mode behind repository interfaces. Store project-owned entities under project subcollections, use transactions/conditional writes for coupled state and activity, and use append-only event/ledger records for replay and idempotency.

## Alternatives Considered

- In-memory dictionaries: useful only for isolated tests; fail restart, concurrency, and multi-instance requirements.
- A document database without project subcollections: would weaken security-rule and tenant boundaries.
- A relational database: viable later, but adds operational surface that is not necessary for the GCP hackathon path.

## Consequences

- Query/index design and emulator tests are mandatory.
- Derived reports can be rebuilt, but mutation entities and activities remain durable.
- A future database migration must preserve repository contracts and event history.
