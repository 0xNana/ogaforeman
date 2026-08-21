# ADR-004: Human Approval and Safety Stops Are Domain Policy

## Status

Accepted

## Context

OG can prepare useful operational actions, but purchases, external commitments, major schedule changes, and safety-critical decisions carry consequences that must remain under qualified human control.

## Decision

Encode approval gates and safety-stop policies as deterministic domain/application policy invoked before tools. Model output may propose an action but cannot bypass policy. Approval decisions are durable, role-checked, versioned, idempotent, and resume persisted workflow checkpoints.

## Consequences

- The UI must show evidence and impact before approval.
- Safety signals stop normal automation and notify a qualified role.
- Policy changes require tests, an ADR or policy version bump, and eval review.
