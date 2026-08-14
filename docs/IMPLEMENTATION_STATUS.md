# Conversational Operations Status

Golden Scenario: PASS

Phase 0 — Audit

Status: COMPLETE

Phase 1 — Intent Router

Status: COMPLETE

Phase 2 — Project Context

Status: COMPLETE

Phase 3 — Conversational Response Layer

Status: COMPLETE

Phase 4 — Entity Resolution

Status: COMPLETE

Phase 5 — Safe Task Operations

Status: COMPLETE

Phase 6 — Safe Material Operations

Status: COMPLETE

Phase 7 — Safe Issue Operations

Status: COMPLETE

Phase 8 — Mutation Policy Engine

Status: ACTIVE

Phases 9–17

Status: NOT STARTED

## Current blockers

- None for local Phase 8 implementation.

## Known regressions

- None.

## Last verified Golden Scenario

- Date: 2026-08-13
- Command: `cd frontend && npm run test:e2e -- site-intake.spec.ts --project=mobile-chromium --reporter=line`
- Result: 7 passed

## Phase 1 evidence

- Typed taxonomy covers casual, query, advice, mutation, site update, clarification,
  confirmation, and unknown messages.
- Structured Gemini output forbids extra fields such as private reasoning.
- Low-confidence mutations route to clarification and cannot enter an action destination.
- Context-free confirmation and clarification responses are rejected safely.
- `SITE_UPDATE` maps to the existing Golden workflow destination.

## Phase 2 evidence

- Query planning selects only the relevant project domains for the nine acceptance questions.
- Retrieval enforces project scope and read permission before accessing persisted state.
- Typed projections cover project, tasks, issues, materials, requests, approvals, schedule,
  daily logs, recent activity, and active project members.
- Today/tomorrow retrieval uses the configured project timezone; operational views filter
  overdue tasks, low stock, pending approvals/requests, and active issues deterministically.
- Results are capped per domain, omit unrelated repositories, and never mutate or emit activity.
- The shared Golden context now includes persisted open issues and pending approvals instead of
  returning hard-coded empty collections.

## Phase 3 evidence

- Casual routing returns a short `What's up?` without requiring project state.
- Project replies are deterministic, concise, and composed only from the authorized Phase 2
  snapshot, with internal record references retained for grounding.
- Overview, today, blockers, overdue work, low materials, pending approvals, tomorrow's work,
  ownership, risk, and honest empty-state responses are covered.
- Operational destinations such as site updates are rejected by the response service and remain
  owned by their existing workflows.
- Persisted user-authored text is treated as display data, not as instructions to the formatter.

## Phase 4 evidence

- Typed resolution covers tasks, issues, materials, material requests, schedule activities,
  active project members, and daily logs.
- Resolution follows project-scoped ID, exact/alias, normalized partial, revalidated context,
  and strong unique fuzzy matching without trusting display names as identity.
- Ambiguous matches return at most five stable clarification candidates and cannot mutate.
- Unknown references and canonical IDs from another project return no entity information.
- Resolution performs no repository writes or activity emission; later mutation phases must
  recheck operation-specific permission before invoking typed tools.

## Phase 5 evidence

- Typed conversational commands cover task creation, completion, status, assignment,
  reassignment, priority, and notes, including timezone-aware planned dates.
- The conversational service composes the existing authorized Task service; it performs no
  direct repository mutation and revalidates resolved canonical task/member IDs.
- Task mutations and their `ActivityEvent` are atomic and idempotent. Replayed commands return
  persisted state without another task version or activity.
- Negated or ambiguous completion is rejected, viewer mutations fail authorization, cancellation
  retains its approval gate, and inactive assignees are rejected inside the transaction.
- Verification: 13 focused task-operation tests passed; Ruff and mypy passed; 370 non-backing
  backend tests and all 7 mobile Golden Scenario tests passed on 2026-08-14.

## Phase 6 evidence

- Typed conversational operations cover material creation, absolute on-site stock, required
  quantity, partial/full deliveries, and notes through existing material services and tools.
- Absolute inventory is calculated inside the transaction, writes an append-only ledger entry,
  and replays without recalculating or duplicating stock.
- Deliveries validate the resolved request/material/unit relationship, persist cumulative received
  quantity, and mark the request delivered only when the approved amount is fully received.
- Material-risk statements are rejected from the direct mutation path for routing into the
  existing shortage/schedule reasoning workflow.
- Verification: 12 focused unit tests, 3 Firestore emulator tests, Ruff, mypy, 377 non-backing
  backend tests, and all 7 mobile Golden Scenario tests passed on 2026-08-14.

## Phase 7 evidence

- Typed conversational issue commands create, assign, change status, resolve, and add notes by
  composing the authorized Issue service and canonical entity resolution.
- Clear positive evidence is required for resolution; negated or ambiguous language cannot mutate.
- Assignment revalidates active project membership inside the atomic mutation transaction.
- Every successful operation persists one issue change with one idempotent activity event.
