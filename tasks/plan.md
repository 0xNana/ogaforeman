# Oga Foreman V1 Execution Plan

## Conversational Operations — Phase 16: Conversational Evals

Acceptance: ship a versioned deterministic benchmark covering every Phase 16 category; compare
typed intent, route, response, entity, policy, approval, audit, mutation, replay, conflict, and
multi-turn outcomes; reject incomplete datasets and fail on safety/control regressions; retain the
existing site-update and Golden Scenario gates.

Implementation slices:

1. Define strict conversational eval schemas, required-category validation, metrics, and report.
2. Add a locked dataset with all 17 required categories and adversarial variants.
3. Add deterministic adapters and independent negative controls for mutation, approval,
   permission, duplicate, stale-state, and multi-turn regressions.
4. Add a CLI/artifact gate, CI-compatible tests, documentation, and phase evidence.
5. Run adversarial review, all static/full suites, both eval gates, and the Golden Scenario.

Status: complete locally on 2026-08-14. Phase 17 final conversational Golden Flow is active.

## Conversational Operations — Phases 11–15

Acceptance: provide cited read-only advice; retain bounded per-user/project references without
using memory as project truth; expose the versioned conversation contract in the responsive Ask
OG drawer; audit significant observable conversation transitions without private reasoning; and
apply the same idempotency and optimistic-concurrency controls as direct operations.

Verification: focused advice, memory, API, audit, mutation, and drawer tests; Ruff, formatting,
mypy, frontend lint/typecheck/tests/build, full non-backing backend tests, and the canonical mobile
Golden Scenario.

Status: complete locally on 2026-08-14. Phase 16 conversational evals is active.

## Conversational Operations — Phase 10: Unified Site Update Routing

Acceptance: route text/chat site facts into existing durable intake and the Golden workflow with
project scope, idempotency, outbox, and AgentRun evidence; no duplicate chat path.

Status: complete locally on 2026-08-14. Phase 11 advice mode is active.

## Conversational Operations — Phase 9: Schedule Operations

Acceptance: resolve scheduled tasks, calculate downstream dependency impact, propose before write,
require deterministic confirmation/approval policy, and atomically shift supported dates.

Status: complete locally on 2026-08-14.

## Conversational Operations — Phase 8: Mutation Policy Engine

Acceptance: deterministically classify supported mutations as auto-execute, confirm-first,
approval-required, or deny/escalate using typed policy inputs and existing authorization.

Status: complete locally on 2026-08-14.

## Conversational Operations — Phase 7: Safe Issue Operations

Acceptance: create, assign, change status, resolve, and annotate project issues through typed
services, canonical entities, positive resolution evidence, and atomic idempotent activity.

Status: complete locally on 2026-08-14.

## Conversational Operations — Phase 6: Safe Material Operations

Acceptance: create materials and safely record absolute stock, requirements, notes, and partial or
full deliveries through typed services; retain append-only ledger, authorization, idempotency, and
existing material-risk workflow ownership.

Verify: focused unit and Firestore restart tests, Ruff, mypy, full non-backing backend tests, and
the canonical mobile Golden Scenario remain green.

Status: complete locally on 2026-08-14.

## Conversational Operations — Phase 5: Safe Task Operations

Acceptance: create and safely update tasks through existing typed services; require resolved,
project-scoped identities; preserve approval and completion safeguards; and atomically emit one
activity event per idempotent mutation.

Verify: focused operation tests, Ruff, mypy, the full non-backing backend suite, and the canonical
mobile Golden Scenario remain green.

Status: complete locally on 2026-08-14.

## Conversational Operations — Phase 4: Entity Resolution

Acceptance: resolve every documented conversational entity from the authorized project partition
using canonical ID, aliases/names, normalized partial matches, revalidated context, and a strict
unique fuzzy threshold; ambiguous or unknown references must remain non-actionable.

Verify: all seven entity kinds, material alias reuse, bounded ambiguity, contextual kind checks,
cross-project ID isolation, fuzzy thresholds, existing Golden resolution, full backend checks, and
the canonical mobile Golden Scenario remain green.

Status: complete locally on 2026-08-13.

## Conversational Operations — Phase 3: Response Layer

Acceptance: produce concise casual and project replies grounded only in the authorized Phase 2
snapshot; cover operational overview and focused query/empty states; retain internal grounding
references; and refuse site-update or action destinations owned by other workflows.

Verify: focused response, context, and intent tests pass; static checks and the full non-backing
suite remain green; the canonical mobile Golden Scenario still passes.

Status: complete locally on 2026-08-13.

## Conversational Operations — Phase 2: Project Context

Acceptance: retrieve permission-aware, query-relevant, bounded typed projections for project,
task, issue, material, request, approval, schedule, daily-log, activity, and member facts from
persisted project state without mutation or reliance on conversational memory.

Verify: the nine documented query shapes select relevant domains; cross-project reads fail;
today/tomorrow use project timezone; low, overdue, pending, and active views are deterministic;
the backend and Golden Scenario regression suites remain green.

Status: complete locally on 2026-08-13. Phase 3 (conversational response layer) is active and
not implemented.

## Conversational Operations — Phase 1: Intent Router

Acceptance: classify conversational input into a typed, non-mutating intent decision; reject
context-free confirmation/clarification replies; prevent low-confidence mutations from entering
an action route; and map site updates to the existing Golden workflow rather than duplicating its
fact interpretation or mutations.

Verify: focused intent taxonomy and Gemini structured-output tests pass, the non-backing backend
suite stays green, and the canonical mobile Golden Scenario passes.

Status: complete locally on 2026-08-13.

## How to Use This Plan

Work top to bottom. A task is one focused session and should normally touch no more than five files. Keep the repository runnable after every task. Mark the matching item in `tasks/todo-v1.md`, update `docs/STATUS.md`, and record contract changes before starting dependent work.

## P0 Winning Vertical Slice Recovery

### P0.1: Real multimodal intake

Acceptance: the claimed site-update worker retrieves verified audio and image bytes
from durable private storage. Audio is transcribed by the configured Gemini adapter,
the transcript and source attachment IDs persist on `SiteUpdate`, and normal
interpretation consumes the transcript. Images and authorized project context reach
Gemini as one structured request; visual-only completion claims remain clarification
candidates until corroborated. Processing failures persist a retryable failed run,
and replay reuses the same update and any already-persisted transcript.

Verify: API-to-worker tests for voice success/replay, retry after transcription,
retry after later interpretation failure, photo byte/context delivery, and ambiguous
visual completion; Gemini SDK request-shape tests; private Storage byte-read tests;
Firestore restart/replay test for a mixed audio/photo update.

Dependencies: F-07, A-02, A-03, A-04, W-01, W-02.

Files: `app/agents/interpreter.py`, `app/agents/site_update_execution.py`,
`app/infrastructure/gemini.py`, `app/infrastructure/storage.py`,
`app/services/site_update_lifecycle.py`, `app/services/site_updates.py`,
`tests/integration/test_site_update_api.py`,
`tests/integration/test_worker_site_update_firestore.py`,
`tests/unit/test_gemini.py`.

Status: complete locally on 2026-08-09. Exact inline Gemini media construction is
covered. A live audio request reached Gemini but was blocked by depleted AI Studio
prepayment credits (`429 RESOURCE_EXHAUSTED`).

### P0.2: Remove the fake browser E2E workflow

Acceptance: browser site-update submissions use the production worker entry point,
coordinator, structured fact routing, typed mutation services, approval service,
outbox continuation, and original-run resume logic against Firestore. The local E2E
stack may replace Gemini, Cloud Storage, and Pub/Sub delivery at their external
boundaries, but no adapter may infer domain state, branch on trigger phrases, or
fabricate run/approval status. Browser tests must observe the persisted approval,
approve it through the API-backed UI, and prove that the same run completes with one
guarded supplier submission.

Verify: API-to-worker integration proves duplicate intake, structured mutations,
durable approval pause, outbox continuation, same-run completion, and exactly-once
external action against both repository implementations. Firestore attachment
sign/verify proves atomic audit writes. Mobile Chromium covers text approval/resume,
real MediaRecorder voice intake, signed photo clarification, invalid media, and a
recoverable persisted worker failure without request interception.

Dependencies: P0.1, K-01 through K-06, A-02 through A-05, W-01 through W-05,
M-01 through M-04, S-03 through S-05.

Files: `scripts/run_e2e_api.py`, `tests/integration/test_e2e_runtime.py`,
`app/services/attachments.py`, `tests/integration/test_uploads.py`,
`frontend/e2e/site-intake.spec.ts`, `frontend/playwright.config.ts`,
`frontend/components/site-composer.tsx`.

Status: complete locally on 2026-08-09. The browser stack uses the Firestore
emulator and deterministic adapters only for model, object storage, and event
transport boundaries; all workflow state is produced by production application
code.

### P0.3: Durable backing services

Acceptance: the production-backed site-update slice persists its `SiteUpdate`,
attachment metadata and original object bytes, transcript, task changes, issues,
material state, approval, `AgentRun`, and `ActivityEvent` records across fresh
Firestore and Cloud Storage clients. A run waiting for approval must be approved
after one restart and resumed after another, completing the same run exactly once.
The CI backend gate must start Firestore and Storage emulators and execute every
backing-service test instead of accepting conditional skips or in-memory restart
substitutes.

Verify: one multimodal API-to-worker test uploads actual audio/photo objects to the
Storage emulator, reaches `WAITING_FOR_APPROVAL`, reconstructs both backing-service
clients, verifies every persisted entity, approves, reconstructs the worker store,
resumes the original run, suppresses replay, and re-reads both media objects.
The normal backend suite excludes the registered `backing_services` marker; Firebase
`emulators:exec --only firestore,storage` then runs that marker with zero skips.

Dependencies: P0.1, P0.2, F-05, F-07, K-01 through K-06, W-01 through W-05,
M-01 through M-04.

Files: `.github/workflows/ci.yml`, `firebase.json`, `firebase/storage.rules`,
`app/infrastructure/storage.py`, `tests/integration/test_worker_site_update_firestore.py`,
`tests/integration/test_*`, `tests/unit/test_infrastructure_manifests.py`,
`pyproject.toml`.

Status: complete locally on 2026-08-09. The standard suite passes 281 tests with
20 backing-service cases deselected; the Firestore/Storage emulator gate executes
all 20 separately with no skips.

### P0.4: Natural-language blocker impact

Acceptance: an actionable `IssueFact` classified as a blocker resolves only to an
authorized project task, transitions that task to `blocked`, and routes its canonical
ID through the dependency-impact service. A separate delay-risk issue references only
the downstream task IDs present in the project graph. Both blocker and schedule risk
project into the daily report, while the same concise risk summary and pending review
action persist on the originating `AgentRun` and are returned by the run API. No
construction phrase or task title controls dependency selection.

Verify: a production-worker test interprets a generic absence statement, blocks
electrical rough-in, traverses direct and transitive test dependencies, excludes an
unrelated task, persists two audited issues and report facts, and exposes the dynamic
task titles in the worker response. The canonical mixed API, Firestore/Storage restart,
and mobile browser journeys use a seeded electrical-to-plastering dependency and prove
the durable run response survives the approval pause.

Dependencies: P0.1 through P0.3, A-02 through A-04, K-02, K-03, B-01, W-02, W-04.

Files: `app/services/site_updates.py`, `app/domain/models.py`,
`app/services/site_update_lifecycle.py`, `app/api/v1/agent_runs.py`,
`scripts/seed_demo.py`, `scripts/run_e2e_api.py`, relevant integration/browser tests.

Status: complete locally on 2026-08-09. All 20 backing-service cases pass with
fresh Storage clients and the existing Firestore emulator; the six-case mobile intake
journey passes with the dependency-derived risk visible in Oga's receipt.

### P0.5: Real follow-through actions

Acceptance: each task-linked blocker creates one explicit operational follow-up
through the typed task service rather than stopping at an `Issue`. The task inherits
the blocked task's canonical assignee when present, persists source references to the
site update, blocker issue, and blocked task, and atomically emits an activity. The
same event/idempotency scope replays without another task. Active follow-ups project
into both Tasks and Needs You. Material risk continues to calculate its shortage from
persisted stock/requirements, create one request and approval, and pause the original
run before any supplier action.

Verify: production-worker and API tests assert the assigned source-linked follow-up,
activity causality, duplicate suppression, 30-bag calculated request, pending approval,
and original-run wait. The Firestore/Storage restart case re-reads the follow-up before
approval and after continuation. Mobile Chromium submits the mixed update, sees the
follow-up in Tasks and Needs You, approves the material request, and observes the same
run complete.

Dependencies: P0.1 through P0.4, K-02, K-03, W-01 through W-04, M-01 through M-03,
B-01, S-01 through S-05.

Files: `app/domain/models.py`, `app/services/tasks.py`, `app/tools/tasks.py`,
`app/services/site_updates.py`, `app/api/v1/projections.py`, the Tasks/Needs You
components, and relevant unit/integration/backing/browser tests.

Status: complete locally on 2026-08-09. The non-backing suite passes 285 tests and
all 20 backing-service cases pass with the new follow-up reloaded through fresh
Firestore clients; the focused mobile production-path journey also passes.

### P0.6: True pause and resume

Acceptance: the voice-only canonical update consumes durable audio while its
`SiteUpdate` is `PROCESSING` and original `AgentRun` is `RUNNING`, then persists the
update, request, and run in `WAITING_FOR_APPROVAL` / `AWAITING_APPROVAL` states. An
approval decision does not execute the supplier action inline. Its claimed
continuation reloads and validates the persisted decision, resolver, linked request,
and exact source run, atomically records resume and terminal run activities, and
executes the guarded supplier action once. Rejection preserves decision notes,
cancels the request, terminalizes the same run, and can never enter the supplier
branch. Both branches survive fresh Firestore and Storage clients while waiting.

Verify: a parameterized backing-service test uploads actual voice bytes, captures the
typed processing states inside interpretation, reconstructs clients before decision
and continuation, and separately approves and rejects. Approval asserts the same
daily-site-update run completes with one submission/outbox claim and one each of
`agent_run.resumed`, `material_request.submitted`, and `agent_run.completed`.
Rejection asserts persisted notes, no supplier outbox/activity, and one
`agent_run.rejected`. Duplicate intake and continuation delivery are suppressed.

Dependencies: P0.1 through P0.5, K-01, K-02, K-06, W-01, W-02, M-02 through M-04.

Files: `app/workflows/resume.py`, `app/worker.py`,
`tests/workflows/test_approval_resume.py`,
`tests/integration/test_worker_site_update_firestore.py`.

Status: complete locally on 2026-08-09. The non-backing suite passes 287 tests and
all 22 backing-service cases pass; the six-case mobile production-path intake suite
also passes.

### P0.7: Complete auditability

Acceptance: retain every existing mutation activity and add a typed, durable
workflow timeline for observable intake, media processing, authorized context
retrieval, structured interpretation, blocker/material/schedule decisions, report
updates, approval pause, continuation, external execution, and terminal completion.
Transition events carry only bounded IDs, counts, statuses, quantities, and
user/debugger-appropriate reasons; prompts, raw media, credentials, signed URLs, and
private model reasoning never enter the audit record. Every event is source/run
linked and replay-safe. The authorized AgentRun API exposes its full public lifecycle
contract, including `updated_at` and stable error fields.

Verify: the canonical multimodal approval and rejection paths assert the required
semantic event set, safe metadata, causal run/source references, single occurrence
under replay, and persistence across fresh Firestore/Storage clients. Contract tests
cover audit-only idempotency and restricted metadata. API tests assert `run_id`,
project, trigger, workflow, status, step, attempt, trace, start/update/complete times,
and error fields.

Dependencies: P0.1 through P0.6, K-01, K-02, K-06, A-01, W-01 through W-04,
M-02 through M-04, B-01, S-01.

Files: `app/domain/activity.py`, `app/domain/models.py`, `app/services/activity.py`,
site-update/approval/external-action workflow services, `app/api/v1/agent_runs.py`,
and relevant contract/integration/backing tests.

Status: complete locally on 2026-08-09. The non-backing suite passes 290 tests,
all 22 Firestore/Storage backing-service cases pass with no skips, and the six-case
mobile production-path intake journey passes. The restart matrix reconstructs the
required voice approval/rejection timeline with one event per replay-safe transition.

## Dependency Graph

```text
configuration/tooling
  -> domain schemas and policies
    -> repository interfaces and Firestore
      -> auth, idempotency, activity, typed tools
        -> coordinator and structured interpreter
          -> Daily Site Update vertical slice
            -> Materials + approvals
            -> Blockers + safety
            -> Daily Brief + scheduler/events
              -> versioned API
                -> Next.js UI
                  -> E2E, observability, deployment, demo
```

## Phase 0: Contract Freeze

### P0-01: Publish product and engineering contracts

Acceptance: the docs index, product spec, engineering spec, production controls, status baseline, and ADRs exist; assumptions and open questions are explicit.

Verify: link scan and human review of `docs/PRODUCT.md` and `docs/ENGINEERING_SPEC.md`.

Dependencies: none.

Files: `docs/*.md`, `docs/decisions/*.md`, `AGENTS.md`.

Scope: M.

### P0-02: Review and approve production assumptions

Acceptance: the user confirms or changes the target stack, public-beta reliability targets, approval policy, authentication direction, and four-workflow scope; decisions are reflected in specs/ADRs.

Verify: no unresolved assumption changes a foundation interface; review outcome is recorded in `docs/STATUS.md`.

Dependencies: P0-01.

Files: `docs/PRODUCT.md`, `docs/ENGINEERING_SPEC.md`, `docs/SLOS.md`, `docs/STATUS.md`.

Scope: S.

### Checkpoint P0

- Human confirms assumptions, target stack, approval policy, and the four-workflow scope.
- No feature implementation proceeds on an unreviewed contract change.

## Phase 1: Foundation

### F-01: Lock development tooling

Acceptance: Python dev dependencies are installable; pytest, ruff, mypy, frontend lint/type/test commands are defined; generated files are ignored.

Verify: `uv sync --all-extras --locked`, `npm ci --ignore-scripts`, backend pytest/ruff/mypy, and frontend audit/lint/typecheck/test.

Dependencies: P0-01.

Files: `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `frontend/package.json`, `frontend/package-lock.json`.

Scope: S.

### F-02: Add typed runtime configuration

Acceptance: one settings object validates environment, model, cloud resources, limits, policy version, and demo mode; missing production values fail fast.

Verify: settings unit tests for local, production, missing secret, invalid limit, and timezone cases.

Dependencies: F-01.

Files: `app/config/settings.py`, `app/config/__init__.py`, `.env.example`, `tests/unit/test_settings.py`.

Scope: M.

### F-03: Implement domain enums and entities

Acceptance: Pydantic/domain models cover the entities and invariants in `DOMAIN_MODEL.md`; all timestamps are timezone-aware; IDs are canonical.

Verify: unit tests for status transitions, dependency cycles, quantity/percentage validation, and naive datetime rejection.

Dependencies: F-01.

Files: `app/domain/models.py`, `app/domain/enums.py`, `app/domain/policies.py`, `tests/unit/test_domain.py`.

Scope: M.

### F-04: Define repository interfaces and in-memory test adapter

Acceptance: application code depends on repository protocols; fake repositories support transactions/version checks and are isolated per test.

Verify: repository contract tests run against a fresh fake for every test and pass concurrent version conflict cases.

Dependencies: F-03.

Files: `app/repositories/interfaces.py`, `app/repositories/memory.py`, `app/repositories/__init__.py`, `tests/contract/test_repositories.py`.

Scope: M.

### F-05: Add Firestore repositories and emulator seed/reset

Acceptance: project-owned entities persist in the documented subcollections; transactions couple mutation and activity; seed/reset is environment-guarded and idempotent.

Verify: emulator integration test creates two projects, restarts the service, resets twice, and proves isolation.

Dependencies: F-04.

Files: `app/infrastructure/firestore.py`, `app/repositories/firestore.py`, `scripts/seed_demo.py`, `scripts/reset_demo.py`, `tests/integration/test_firestore_repositories.py`.

Scope: M.

### F-06: Implement identity and project authorization

Acceptance: authenticated user context and role checks are available to API, repositories, and tools; cross-project access is rejected.

Verify: authorization matrix tests for admin/manager/foreman/viewer and two projects.

Dependencies: F-03, F-05.

Files: `app/api/auth.py`, `app/domain/authorization.py`, `app/repositories/membership.py`, `tests/integration/test_authorization.py`.

Scope: M.

### F-07: Implement secure attachment intake

Acceptance: signed upload requests are project-scoped, short-lived, size/type limited, checksum-verified, and represented by `Attachment` metadata.

Verify: upload contract tests for valid, expired, forged-path, oversized, invalid-type, and checksum mismatch cases.

Dependencies: F-05, F-06.

Files: `app/api/uploads.py`, `app/infrastructure/storage.py`, `app/services/attachments.py`, `tests/integration/test_uploads.py`.

Scope: M.

### Checkpoint F

- Firestore emulator and fake repository tests pass.
- Restart, authorization, timestamp, and upload controls pass.
- No production path imports `_PROJECT_DB`.

## Phase 2: Mutation and Event Kernel

### K-01: Add event envelope, claims, and idempotency

Acceptance: all registered event types validate; claims are atomic; duplicates return prior result references; expired claims can be reclaimed.

Verify: duplicate delivery and concurrent claim integration tests.

Dependencies: F-05, F-06.

Files: `app/domain/events.py`, `app/services/event_claims.py`, `app/repositories/event_claims.py`, `tests/contract/test_events.py`, `tests/integration/test_event_claims.py`.

Scope: M.

### K-02: Build activity/audit service

Acceptance: mutation context is mandatory; domain writes and activity records commit atomically; summaries exclude hidden reasoning/secrets.

Verify: mutation contract tests assert actor, source event, run, entity, and exactly-once activity behavior.

Dependencies: F-04, F-05, K-01.

Files: `app/services/activity.py`, `app/repositories/activity.py`, `app/domain/activity.py`, `tests/contract/test_activity.py`.

Scope: M.

### K-03: Replace task tools with typed repository-backed tools

Acceptance: task updates resolve existing authorized IDs, enforce status/dependency invariants, support idempotency, and emit activities.

Verify: tool matrix for valid update, negated update, duplicate, conflict, forbidden project, and blocked completion.

Dependencies: F-03, F-06, K-02.

Files: `app/tools/tasks.py`, `app/services/tasks.py`, `app/repositories/tasks.py`, `tests/unit/test_task_tools.py`, `tests/integration/test_task_tools.py`.

Scope: M.

### K-04: Implement canonical material identity and ledger tools

Acceptance: materials use canonical IDs/aliases/units; quantity changes are append-only ledger entries; negative stock and unknown units are rejected.

Verify: alias, unit conversion policy, duplicate ledger event, concurrent update, and negative quantity tests.

Dependencies: F-03, F-06, K-02.

Files: `app/domain/materials.py`, `app/services/materials.py`, `app/repositories/materials.py`, `app/tools/materials.py`, `tests/unit/test_material_tools.py`.

Scope: M.

### K-05: Add structured API errors and rate limits

Acceptance: API errors match `API.md`; intake/upload/model work has per-user/project limits with retry headers; logs contain request IDs.

Verify: API contract and burst-limit tests.

Dependencies: F-02, F-06, F-07.

Files: `app/api/errors.py`, `app/api/limits.py`, `app/api/dependencies.py`, `tests/integration/test_api_errors_limits.py`.

Scope: M.

### K-06: Add outbox claims for notifications and external actions

Acceptance: notifications and supplier actions have persisted claims, retry status, and deduplication keys; a retry cannot repeat a completed side effect.

Verify: outbox contract tests for success, crash-before-ack, retry, and duplicate delivery.

Dependencies: K-01, K-02.

Files: `app/services/outbox.py`, `app/repositories/outbox.py`, `app/services/notifications.py`, `tests/integration/test_outbox.py`.

Scope: M.

## Phase 3: Agent Kernel

### A-01: Create typed agent registry

Acceptance: coordinator and four specialists have one canonical name/description/prompt version/tool allowlist; startup validates references.

Verify: registry completeness and duplicate-name tests.

Dependencies: F-02, K-03, K-04.

Files: `app/agents/registry.py`, `app/agents/factory.py`, `app/prompts/manifest.yaml`, `tests/unit/test_agent_registry.py`.

Scope: M.

### A-02: Implement structured SiteInterpreter adapter

Acceptance: fake and Gemini adapters return validated `ExtractedFactSet` with evidence, confidence, negation, and clarification fields.

Verify: eval fixtures for explicit completion, absence/negation, ambiguity, material quantity, and safety.

Dependencies: F-02, A-01.

Files: `app/agents/interpreter.py`, `app/domain/facts.py`, `app/infrastructure/gemini.py`, `tests/unit/test_interpreter.py`, `evals/site_updates.json`.

Scope: M.

### A-03: Build bounded project context and entity resolution

Acceptance: context contains only authorized relevant entities; task/material matching returns candidates and confidence; unknown/ambiguous matches clarify.

Verify: overlapping-name, cross-project, alias, and ambiguous-match tests.

Dependencies: F-03, F-06, K-03, K-04, A-02.

Files: `app/services/context.py`, `app/services/entity_resolution.py`, `app/repositories/context.py`, `tests/unit/test_entity_resolution.py`.

Scope: M.

### A-04: Route facts through policy before mutation

Acceptance: explicit positive facts can proceed; negated/ambiguous facts cannot complete/update progress; safety facts trigger stop policy; high-impact actions require approval.

Verify: policy matrix tests mapped to `PRODUCTION_READINESS.md`.

Dependencies: A-02, A-03, K-03, K-04.

Files: `app/domain/policies.py`, `app/services/fact_router.py`, `tests/unit/test_fact_router.py`, `tests/unit/test_safety_policy.py`.

Scope: M.

### A-05: Route every production event through OgaCoordinator

Acceptance: API and worker entrypoints invoke one coordinator service; direct workflow calls are limited to tests/demo adapters; coordinator route names resolve through the registry.

Verify: API-to-coordinator and Pub/Sub-to-coordinator integration tests assert one run and one route decision.

Dependencies: A-01, A-04, K-01.

Files: `app/agents/coordinator.py`, `app/services/event_router.py`, `app/api/events.py`, `tests/integration/test_coordinator_routing.py`.

Scope: M.

## Phase 4: Daily Site Update Vertical Slice

### W-01: Persist workflow runs and checkpoints

Acceptance: runs/checkpoints survive worker restart and expose safe status summaries.

Verify: kill/restart worker between steps and resume test.

Dependencies: K-01, K-02, A-01.

Files: `app/workflows/runtime.py`, `app/repositories/runs.py`, `tests/workflows/test_runtime.py`.

Scope: M.

### W-02: Implement Daily Site Update orchestration

Acceptance: API/event path invokes `OgaCoordinator`, fans out branches, joins results, updates report, and emits response/activity.

Verify: canonical mixed update workflow test and API-to-coordinator integration test.

Dependencies: A-04, W-01, K-03, K-04.

Files: `app/workflows/site_update.py`, `app/agents/coordinator.py`, `app/services/site_updates.py`, `tests/workflows/test_site_update.py`.

Scope: M.

### W-03: Add clarification and safety stop branches

Acceptance: ambiguous updates wait for clarification; credible safety/structural issues stop unsafe branches and notify qualified roles.

Verify: ambiguity and safety E2E/workflow tests.

Dependencies: W-02, A-04.

Files: `app/workflows/clarification.py`, `app/workflows/safety.py`, `app/services/notifications.py`, `tests/workflows/test_clarification_safety.py`.

Scope: M.

### W-04: Persist daily report projection and response

Acceptance: report is unique per project/date, source-linked, replay-safe, and returns a concise summary with pending actions.

Verify: report rebuild and duplicate replay tests.

Dependencies: W-02, K-02.

Files: `app/services/reports.py`, `app/repositories/reports.py`, `app/agents/reporter.py`, `tests/integration/test_reports.py`.

Scope: M.

### W-05: Remove prototype keyword and hard-coded-ID mutation paths

Acceptance: production workflows use structured facts and entity resolution only; prototype keyword adapters are isolated under an explicit demo/test module or removed.

Verify: static search for hard-coded task IDs/keyword mutation branches plus new-task/paraphrase regression tests.

Dependencies: A-03, A-04, W-02.

Files: `app/workflows/site_update.py`, `app/services/fact_router.py`, `tests/workflows/test_site_update.py`, `docs/STATUS.md`.

Scope: M.

### Checkpoint W

- Canonical demo update works from API input through durable state and activity.
- Duplicate delivery and worker restart tests pass.
- No hard-coded task IDs or keyword mutation paths remain in production workflow code.

## Phase 5: Materials and Approvals

### M-01: Implement shortage calculation and request workflow

Acceptance: stock, reservations, upcoming task requirements, needed-by, and request deduplication are persisted and typed.

Verify: in-stock, shortage, duplicate, and missing-unit cases.

Dependencies: K-04, W-01.

Files: `app/workflows/materials.py`, `app/services/material_requests.py`, `tests/workflows/test_materials.py`.

Scope: M.

### M-02: Implement approval state machine and continuation events

Acceptance: approve/reject is role/version/idempotency checked; rejection closes request branch; approval resumes persisted run after restart.

Verify: approval conflict, rejection, restart/resume, and duplicate decision tests.

Dependencies: K-01, K-02, M-01.

Files: `app/services/approvals.py`, `app/repositories/approvals.py`, `app/workflows/resume.py`, `tests/workflows/test_approvals.py`.

Scope: M.

### M-03: Make approval pause/resume restart-safe

Acceptance: an `AgentRun` waiting for approval persists its checkpoint; after worker restart, one approved decision resumes the same run and one rejection closes the linked request.

Verify: kill/restart, duplicate decision, rejection, and external-action-not-called tests.

Dependencies: M-02, W-01, K-06.

Files: `app/workflows/resume.py`, `app/services/approvals.py`, `app/repositories/runs.py`, `tests/workflows/test_approval_resume.py`.

Scope: M.

### M-04: Add simulated supplier and delivery-delay adapter

Acceptance: approved requests produce one claimed simulated action; status events include delayed delivery and preserve request history.

Verify: outbox claim and delayed delivery replay tests.

Dependencies: M-03, K-01, K-06.

Files: `app/infrastructure/supplier_simulator.py`, `app/services/external_actions.py`, `tests/integration/test_supplier_simulator.py`.

Scope: M.

## Phase 6: Blockers and Daily Brief

### B-01: Implement dependency impact analysis

Acceptance: blocker facts resolve task/dependency graph, calculate transparent projected impact, and create risk/owner actions.

Verify: dependency chain, no-dependency, cycle rejection, and delivery-delay tests.

Dependencies: F-03, A-03, W-01.

Files: `app/services/schedule_impact.py`, `app/workflows/blockers.py`, `tests/workflows/test_blockers.py`.

Scope: M.

### B-02: Add safety escalation and resolution tracking

Acceptance: safety stop policy is enforced, qualified role is notified, acknowledgement is recorded, and issue resolution updates risk.

Verify: critical safety workflow and resolution tests.

Dependencies: W-03, B-01.

Files: `app/services/safety.py`, `app/services/issues.py`, `tests/integration/test_safety.py`.

Scope: M.

### D-01: Implement scheduled Daily Brief

Acceptance: scheduler event creates one source-linked brief per project/window and notification; missing data is not invented.

Verify: scheduled event, duplicate event, empty project, and notification retry tests.

Dependencies: W-04, K-01, K-02.

Files: `app/workflows/daily_brief.py`, `app/services/daily_brief.py`, `tests/workflows/test_daily_brief.py`.

Scope: M.

### E-01: Connect Pub/Sub/Eventarc worker entrypoint

Acceptance: API publishes normalized events; worker claims and routes them through coordinator; dead-letter and retry metadata are preserved.

Verify: emulator end-to-end event delivery, duplicate, retry, and dead-letter tests.

Dependencies: K-01, W-01, W-02.

Files: `app/worker.py`, `app/infrastructure/pubsub.py`, `app/api/events.py`, `tests/integration/test_event_delivery.py`.

Scope: M.

### E-02: Add Cloud Scheduler configuration

Acceptance: daily brief events are scheduled per environment/project policy and never run twice for the same window.

Verify: infrastructure validation and duplicate scheduler event tests.

Dependencies: D-01, E-01.

Files: `infra/scheduler.*`, `scripts/register_schedules.py`, `tests/integration/test_scheduler_events.py`.

Scope: S.

## Phase 7: Versioned API and UI

### S-01: Build versioned FastAPI routers and projections

Acceptance: project/state/task/material/issue/report/activity/run routes match `API.md`, enforce auth, pagination, errors, and no process-global state.

Verify: OpenAPI/contract tests and authorization matrix.

Dependencies: F-06, K-02, W-02, M-02.

Files: `app/api/v1/*.py`, `app/api/schemas.py`, `tests/contract/test_api.py`, `tests/integration/test_api.py`.

Scope: M.

### S-02: Build Next.js application shell and typed client

Acceptance: project navigation, auth context, query keys, loading/error states, and responsive shell exist without hard-coded project data.

Verify: lint/typecheck, component tests, and browser shell test.

Dependencies: S-01.

Files: `frontend/app/*`, `frontend/components/*`, `frontend/lib/api.ts`, `frontend/tests/*`.

Scope: M.

### S-03: Build mobile site intake flow

Acceptance: text/voice/photo/file intake submits to signed-upload and site-update APIs, displays processing/clarification/error states, and links to results.

Verify: Playwright mobile flow with denied microphone and invalid upload cases.

Dependencies: F-07, S-01, S-02.

Files: `frontend/app/projects/[id]/site/*`, `frontend/components/site-composer/*`, `frontend/tests/site-intake.*`, `e2e/site-update.spec.ts`.

Scope: M.

### S-04: Build command center, approvals, materials, tasks, reports, activity

Acceptance: command center and activity views read API projections, show real status transitions, and handle stale/conflict/error states.

Verify: desktop/mobile Playwright suite and accessibility scan.

Dependencies: S-02, S-03, M-02, D-01.

Files: `frontend/app/projects/[id]/page.tsx`, `frontend/app/projects/[id]/activity/page.tsx`, `frontend/components/command-center/*`, `e2e/manager-flows.spec.ts`.

Scope: M.

### S-05: Build manager resource and approval views

Acceptance: approvals, materials, tasks, issues, and reports render API-backed state and support the documented actions.

Verify: approval approve/reject, stale conflict, and resource browser tests.

Dependencies: S-02, S-04, M-03, D-01.

Files: `frontend/app/projects/[id]/approvals/page.tsx`, `frontend/app/projects/[id]/materials/page.tsx`, `frontend/app/projects/[id]/tasks/page.tsx`, `frontend/components/approval/*`, `e2e/manager-resources.spec.ts`.

Scope: M.

### S-06: Remove static UI state and hard-coded metrics

Acceptance: no production screen uses demo-only metrics, inline mutation scripts, or client-owned project truth; all data reloads from the versioned API.

Verify: browser fixture changes are reflected after reload and static-state search is clean.

Dependencies: S-04, S-05.

Files: `web/index.html`, `frontend/lib/api.ts`, `frontend/app/projects/[id]/page.tsx`, `frontend/tests/api-backed-state.test.ts`.

Scope: S.

## Phase 8: Reliability, Security, and Launch

### R-01: Complete production-readiness test suite

Acceptance: every PR control has an automated verification case; all core eval thresholds pass.

Verify: commands in `PRODUCTION_READINESS.md`.

Dependencies: all prior feature tasks.

Files: `tests/production_readiness/*`, `evals/*`, `scripts/run_evals.py`, `docs/STATUS.md`.

Scope: M.

### R-02: Add eval runner and regression artifacts

Acceptance: the locked dataset runs with fake and configured model adapters, reports mutation diffs, and enforces thresholds in `EVALS.md`.

Verify: normal/mixed/ambiguous/negation/approval/duplicate/safety/delivery cases and a deliberate regression.

Dependencies: A-02, W-02, M-03, B-02.

Files: `evals/*.json`, `scripts/run_evals.py`, `tests/evals/test_regressions.py`, `docs/STATUS.md`.

Scope: M.

### R-03: Add observability and operational controls

Acceptance: structured logs, traces, metrics, alerts, dead-letter inspection, and run/activity links are available in staging.

Verify: staging smoke and trace correlation test.

Dependencies: E-01, S-01, W-01.

Files: `app/observability/*`, `app/api/health.py`, `infra/monitoring.*`, `tests/integration/test_observability.py`.

Scope: M.

### R-04: Verify load, backup, restore, and recovery objectives

Acceptance: the baseline capacity in `SLOS.md` passes without state corruption; Firestore/Storage protection is enabled; an isolated restore and projection rebuild meet RTO/RPO targets.

Verify: load report, backup job evidence, restore rehearsal, and projection rebuild timing.

Dependencies: F-05, E-01, S-01, R-03.

Files: `tests/load/*`, `scripts/verify_backups.py`, `scripts/rebuild_projections.py`, `docs/SLOS.md`, `docs/STATUS.md`.

Scope: M.

### L-01: Reproducible Cloud deployment

Acceptance: infrastructure and IAM are reviewed/checkable; API and worker deploy separately; smoke and rollback are documented and tested.

Verify: staging deployment and rollback rehearsal.

Dependencies: F-02, E-02, R-03, R-04.

Files: `infra/*`, `Dockerfile`, `.github/workflows/*`, `docs/DEPLOYMENT.md`.

Scope: M.

### L-02: Rehearsable demo and launch evidence

Acceptance: `reset-demo` is safe/idempotent; demo script passes repeatedly; release evidence and known limitations are recorded.

Verify: three consecutive demo runs, including rejection and worker restart rehearsal.

Dependencies: R-01, R-02, R-03, L-01.

Files: `scripts/seed_demo.py`, `scripts/reset_demo.py`, `scripts/run_demo.py`, `docs/DEMO.md`, `README.md`.

Scope: M.

### L-03: Release documentation and known-limitations handoff

Acceptance: README quick start matches implemented commands; status, operations, deployment, and known limitations describe the released revision.

Verify: clean-checkout quick start and docs link scan.

Dependencies: L-02.

Files: `README.md`, `docs/STATUS.md`, `docs/OPERATIONS.md`, `docs/DEPLOYMENT.md`.

Scope: S.

## Checkpoints

### After F-07

Persistence, identity, upload, and time controls pass.

### After W-04

The canonical site update is durable, replay-safe, auditable, and API-triggered.

### After M-04 and B-02

Approval/rejection, restart/resume, delivery delay, dependency impact, and safety stop pass.

### Before launch

All tests/evals, browser flows, observability, deployment smoke, rollback, and `PR-*` controls pass.
