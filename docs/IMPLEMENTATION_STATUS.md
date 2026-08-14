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

Status: COMPLETE

Phase 9 — Schedule Operations

Status: COMPLETE

Phase 10 — Unified Site Update Routing

Status: COMPLETE

Phase 11 — Advice Mode

Status: COMPLETE

Phase 12 — Conversational Memory

Status: COMPLETE

Phase 13 — OG Drawer Integration

Status: COMPLETE

Phase 14 — Conversational Activity & Audit

Status: COMPLETE

Phase 15 — Conflict, Concurrency & Idempotency

Status: COMPLETE

Phase 16 — Conversational Evals

Status: COMPLETE

Phase 17 — Final Conversational Golden Flow

Status: ACTIVE

## Current blockers

- None for local Phase 16 implementation. A configured live-Gemini evaluation is required before
  changing the production conversation prompt or model.

## Known regressions

- None.

## Known Phase 17 integration gaps

- The conversation API currently proposes `PROJECT_ACTION` requests but does not yet dispatch
  routine task, material, or issue mutations through their typed operation services.
- Confirmation replies are classified and remembered, but the API does not yet resume the exact
  persisted proposed command after revalidation.
- Approval-required purchase requests are not yet handed from conversation into the existing
  approval workflow.
- The responsive drawer does not yet render executable confirm/cancel controls for a persisted
  proposed change.

These are explicitly outside the deterministic Phase 16 evaluator's runtime claim and are the
active Phase 17 end-to-end scope.

## Phase 16 evidence

- `evals/conversations_v1.json` covers all 17 required categories with strict schema validation.
- Every release metric is locked at 1.0; incomplete categories, duplicate IDs, invalid thresholds,
  mismatched typed outcomes, missing grounding/audit evidence, and parse failures fail the gate.
- Thirteen isolated guard regressions prove unsafe mutation, approval/external action, permission,
  replay, conflict, memory, audit, and cross-project grounding failures cannot remain green.
- CI runs both the original site-update eval and the conversational eval; the original mobile
  Golden Scenario remains a separate mandatory boundary gate.

## Last verified Golden Scenario

- Date: 2026-08-14
- Command: `cd frontend && npm run test:e2e -- site-intake.spec.ts --project=mobile-chromium --reporter=line`
- Result: 7 passed after preserving the visible multimodal composer in the integrated drawer

## Phase 1 evidence

- Typed taxonomy covers casual, query, advice, mutation, site update, clarification,
  confirmation, and unknown messages.
- Structured Gemini output forbids extra fields such as private reasoning.
- Low-confidence mutations route to clarification and cannot enter an action destination.
- Context-free confirmation and clarification responses are rejected safely.
- `SITE_UPDATE` maps to the existing Golden workflow destination.

## Phase 11–15 evidence

- Advice uses fresh authorized schedule, dependency, material, request, approval, and issue
  context, returns cited proceed/hold/review guidance, and performs no domain mutation.
- Firestore-backed conversational memory is bounded by project and canonical actor and retains
  references rather than entity snapshots; every reference is re-resolved before use.
- The responsive Ask OG drawer renders concise reply, advice, proposed-change, and workflow states
  and retains the existing voice/photo/attachment intake path.
- Significant change-request and confirmation transitions emit allowlisted, idempotent activities;
  routine chatter and private model reasoning are not logged.
- Conversational task, material, and issue commands reject stale expected versions and preserve
  fresh state; duplicate request audit and existing typed domain mutations replay once.

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

## Phase 8 evidence

- A typed deterministic policy classifies supported mutations as auto-execute, confirm-first,
  approval-required, or deny/escalate without relying on model judgment.
- Purchases, commitments, and major schedule actions explicitly retain the existing approval path.
- Unsafe certification/judgment/concealment and insufficient permissions fail closed.

## Phase 9 evidence

- Schedule proposals resolve canonical tasks, traverse downstream dependencies, calculate the
  date delta, and return impact before any mutation.
- Routine schedule changes require explicit confirmation; major changes retain approval policy.
- Confirmed changes shift the selected task and supported downstream dates atomically and replay
  through one persisted activity claim.

## Phase 10 evidence

- Text conversational updates use a typed routing boundary into `SiteUpdateIntakeService`, the
  same durable event, outbox, AgentRun, coordinator, and Golden workflow path used by voice and
  photo intake.
- Routing validates project scope and preserves the supplied idempotency key; it does not create a
  second fact interpreter or chat-specific mutation path.
