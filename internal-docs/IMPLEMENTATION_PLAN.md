# Implementation Plan Overview

This is the phase-level roadmap. The executable, file-scoped task list is [`../tasks/plan.md`](../tasks/plan.md); its canonical evidence checklist is [`../tasks/todo-v1.md`](../tasks/todo-v1.md).

## Phase 0 - Contract Freeze

Complete and review product, domain, event, tool, workflow, API, UI, security, evaluation, and deployment contracts. Resolve open decisions that would change interfaces.

## Phase 1 - Production Foundation

Add typed configuration, dependency locks, lint/type checks, domain entities, repository interfaces, in-memory test repository, Firestore adapter, seed/reset tooling, and project-scoped auth context.

Exit gate: restart-safe persistence tests and two-project tenant isolation pass.

## Phase 2 - Mutation and Audit Kernel

Implement canonical IDs, material ledger, task/dependency invariants, event claims, idempotency fingerprints, transactional mutation tools, activity events, structured errors, rate limits, and upload validation.

Exit gate: all `PR-01` through `PR-06`, `PR-11`, and `PR-12` controls have tests.

## Phase 3 - Agent Kernel

Implement the typed agent registry, coordinator entrypoint, bounded context builder, structured specialist outputs, prompt versioning, model adapter, confidence policy, negation handling, entity resolution, and fake-model test adapter.

Exit gate: interpreter tests prove explicit completion, ambiguity, negation, and unknown entity behavior.

## Phase 4 - Daily Site Update Vertical Slice

Connect intake through event publication, ADK workflow checkpoints, fan-out/fan-in branches, safe mutations, daily report projection, user response, and activity timeline.

Exit gate: the canonical demo input passes end-to-end, including duplicate replay and worker restart before approval.

## Phase 5 - Materials and Approval

Implement material requirements, requests, approval state machine, pause/resume continuation event, simulated supplier adapter, rejection behavior, and manager UI.

Exit gate: `PR-03` through `PR-05` and approval E2E tests pass.

## Phase 6 - Blockers, Delay, and Daily Brief

Implement dependency impact analysis, safety stop/escalation, delivery delay handling, scheduled daily brief events, report persistence, and notifications.

Exit gate: blocker and delayed-delivery evals pass and no unsafe branch mutates state.

## Phase 7 - Product UI

Replace static HTML with Next.js typed API client and responsive command center, mobile intake, approvals, tasks, materials, reports, and activity screens.

Exit gate: API-backed browser flows pass at 360 px and desktop viewports; no hard-coded project metrics remain.

## Phase 8 - Reliability and Operations

Add emulator/integration suites, full eval runner, structured logging, tracing, metrics, alerts, dead-letter handling, migration/rollback scripts, CI, and vulnerability scans.

Exit gate: production readiness suite passes and all release evidence is captured.

## Phase 9 - Launch and Demo Polish

Deploy staging and beta, rehearse reset-safe demo, verify smoke/rollback, publish runbook and architecture diagram, and record known limitations.

Exit gate: the demo is repeatable and no `PR-*` control is open.

## Critical Sequencing

Persistence, identity, idempotency, and audit precede any real autonomous mutation. The UI is built against versioned API projections after those contracts exist. Model quality work uses deterministic fake adapters first so cloud/model availability cannot hide domain bugs.
