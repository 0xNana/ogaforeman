# Oga Foreman V1 Evidence Audit

Audited 2026-08-08 against production paths, tests, artifacts, frontend journeys,
and deployment scripts. This file is the canonical checklist; the legacy
`tasks/todo.md` checklist is retired.

Legend: `[x]` implemented and verified locally; `[~]` partially implemented
or unstable; `[ ]` implementation/evidence missing; `[!]` blocked only on a
real cloud environment, live model credential/billing, or human release gate.

## Audit findings requiring implementation

- [x] G-01 Every coordinator event route executes a deterministic persisted
  workflow mutation set before its claim is completed; replay and Firestore
  restart coverage includes task, material, blocker, overdue, delivery-delay,
  and daily-brief events.
- [x] G-02 The registered ADK manifest exposes no compatibility/demo tools;
  blocker and daily-brief entry points now require repository-backed typed event
  execution, and prototype adapters were removed from production modules.
- [x] G-03 Approval continuation reloads the exact persisted run, claims a
  replay-safe supplier action, processes any delivery-delay event, and completes
  the original material run only after the continuation reaches a terminal result.
- [x] G-04 Daily Brief scheduling produces one repository-backed report,
  activity, notification outbox message, and completed run per reporting event.
- [x] G-05 Mobile Playwright covers text, real browser voice capture, signed photo
  upload, microphone denial, invalid upload, clarification, processing, failure,
  and durable terminal run state through the local `/api/v1` stack.
- [x] G-06 Firestore auth bootstrap uses atomic document creation instead of a
  contended read/write transaction; the 32-call race, three isolated repeats,
  and the complete 92-test emulator integration suite pass.

## Contracts and foundation

- [x] P0-01 Documentation set exists; `scripts/check_docs.py` passes.
- [x] P0-02 Product/engineering assumptions and the four-workflow scope are recorded.
- [x] F-01 `uv sync --all-extras --locked` and normal `npm ci` pass from the
  checked-in lockfiles.
- [x] F-02 Typed settings and `.env.example` are validated; production
  authentication and demo boundaries fail closed.
- [x] F-03 Typed entities, enums, timezone-aware timestamps, and transition
  invariants pass local coverage.
- [x] F-04 Repository protocols and the isolated in-memory adapter pass contract
  and concurrency tests.
- [x] F-05 Firestore repository transaction, restart, isolation, and optimistic
  version tests pass against `127.0.0.1:8085`.
- [x] F-06 Firebase verification, canonical identity, membership, authorization,
  and atomic idempotent bootstrap pass local and emulator integration coverage.
- [x] F-07 Signed upload type, size, checksum, path, authorization, retry, and
  activity controls pass with a fake Storage adapter.

Foundation gate:

- [x] No production module imports `_PROJECT_DB` or uses
  `datetime.utcnow()`.
- [x] All 13 local `PR-*` readiness controls pass without xfails.
- [!] Deployed Firebase token, IAM, Firestore, and Storage enforcement still
  require a real staging project.

## Mutation and event kernel

- [x] K-01 Versioned events, claims, fingerprints, leases, replay suppression,
  and dead-letter metadata pass local/emulator-capable tests.
- [x] K-02 Safe mutations atomically emit an `ActivityEvent`.
- [x] K-03 Task commands enforce authorization, evidence, idempotency, and
  negation policy.
- [x] K-04 Material aliases and append-only ledger rules pass local coverage.
- [x] K-05 Structured errors, request IDs, and bounded rate limits are tested.
- [x] K-06 Outbox claims and retry/deduplication controls are tested.

Kernel gate:

- [x] PR-02, PR-03, PR-04, PR-11, and local error/idempotency controls pass.

## Agent kernel

- [x] A-01 Typed registry and prompt/sub-agent startup validation pass.
- [x] A-02 Fakeable structured interpretation covers normal, mixed, ambiguous,
  negated, material, approval, safety, and delivery fixtures.
- [x] A-03 Authorized bounded context and entity resolution cover aliases,
  ambiguity, unknown entities, and cross-project isolation.
- [x] A-04 Confidence, clarification, approval, and safety routing pass.
- [x] A-05 Every supported event reaches the coordinator and a persisted,
  replay-safe execution path; model interpretation remains isolated to the
  site-update ADK bridge.

Agent gate:

- [x] PR-07, PR-08, PR-09, and PR-10 pass their current local controls.
- [x] The coordinator executes rather than merely labels every V1 event route.

## Daily Site Update workflow

- [x] W-01 Queued/running/failed/completed, clarification, and approval state
  persists through the claimed worker path and Firestore client restart.
- [x] W-02 The ADK site-update path fans out task, issue, material, shortage
  request, and approval mutations, then joins durable results.
- [x] W-03 Clarification and safety-stop branches are covered.
- [x] W-04 The canonical workflow produces one replay-safe source-linked report
  with completed work, blockers, material risks, and next focus.
- [x] W-05 Canonical site-update mutation avoids hard-coded IDs/keywords, and the
  ADK manifest no longer registers prototype or compatibility tools.

Vertical slice gate:

- [x] Mixed text/voice/photo payloads prove durable task, issue, material,
  request, approval, report, activity, attachment, and run state through
  `/api/v1` and Firestore restart.
- [x] Duplicate replay and Firestore client restart are covered through the
  wired site-update worker path.

## Materials, approvals, blockers, briefs, and events

- [x] M-01 Shortage calculation and request deduplication pass service/workflow tests.
- [x] M-02 Rejection atomically closes the linked request and emits continuation.
- [x] M-03 Approval/rejection reload the exact persisted run after restart;
  approved purchase continuation executes supplier and delay steps to completion.
- [x] M-04 Supplier submission is an audited guarded transition; one delayed
  event updates the request, creates downstream risk, queues notification, and
  suppresses replay.
- [x] B-01 Dependency impact calculation passes focused tests.
- [x] B-02 Safety stops persist inside site-update processing, and standalone
  blocker, overdue, and delivery-delay events execute repository-backed workflows.
- [x] D-01 Stable daily-brief events upsert one source-linked report and
  notification through the worker without inventing missing sections.
- [x] E-01 Pub/Sub push, claims, retries, dead-letter metadata, and all typed
  worker event routes execute durable guarded behavior.
- [!] E-02 Scheduler HTTP dispatch now feeds the real Pub/Sub worker push path
  and proves one durable report, activity, processed event, and completed run;
  only the deployed Cloud Scheduler smoke requires cloud resources.

## API and UI

- [x] S-01 Authorized snapshots project persisted resources, latest report, and
  new-project creation activity; emulator onboarding evidence passes.
- [x] S-02 Typed Next.js shell, API client, lint, typecheck, unit tests, and
  production build pass.
- [x] S-03 Mobile composer uses microphone capture, signed attachment upload,
  durable run polling, and checked-in intake/error Playwright journeys.
- [x] S-04 Checked-in Playwright desktop/mobile command-center and activity
  journeys pass, including accessibility and overflow checks.
- [x] S-05 Resource rendering, approve/reject persistence, and recoverable stale
  conflicts pass against the local API stack.
- [x] S-06 Authenticated API mode fails closed; fixtures remain behind explicit
  demo mode.

## Reliability and launch

- [x] R-01 `tests/production_readiness` maps PR-01 through PR-13 and reports
  13 passing controls with no xfails.
- [!] R-02 Fixture eval passes 8/8 thresholds and records per-case mutation
  diffs; a checked-in deliberate-regression adapter proves the gate fails on a
  forbidden negated-task mutation. Only configured Gemini evidence remains.
- [!] R-03 Local logs, metrics, health, dead-letter, and alert definitions pass;
  staging trace correlation and alert smoke require deployed resources.
- [!] R-04 Local capacity and backup dry-run pass; backup visibility, isolated
  restore, Storage recovery, and measured cloud RTO/RPO require staging.
- [!] L-01 Deployment/IAM scripts, CI, container smoke, and dry-run syntax exist;
  staging deploy, authenticated smoke, and rollback rehearsal are not executed.
- [!] L-02 Three deterministic dry runs and local browser/API/Firestore evidence
  pass, including terminal approved-material continuation; live Gemini evidence
  still needs a working external model route.
- [x] L-03 README/status/auth/deployment/operations/demo docs pass, and the
  isolated clean-checkout runner records locked backend/frontend installs,
  static checks, tests, builds, browser journeys, evals, demo, and capacity.

## Latest local evidence

- [x] Backend: 252 passed, 18 emulator-dependent skipped.
- [x] Production readiness: 13 passed, no xfails.
- [x] Firestore repository contract: 8 passed.
- [x] Routed workflow regression: memory scenarios plus Firestore client restart
  persistence pass, including terminal approved-material continuation.
- [x] Firestore emulator integration: 92 passed; the atomic auth bootstrap's
  32-call race also passed three additional isolated repeats.
- [x] Fixture eval: 8/8 cases and mutation-diff thresholds passed.
- [x] Deliberate regression eval: the forbidden negated-task mutation is
  detected and recorded in `artifacts/evals/deliberate-regression.json`.
- [x] Local scheduler-to-worker proof: HTTP dispatch and Pub/Sub push produce
  one durable daily brief mutation set under duplicate delivery.
- [x] Capacity baseline: five scenarios passed.
- [x] Demo rehearsal: three dry runs passed, including approval, rejection,
  replay suppression, worker restart, and delivery delay.
- [x] Frontend: normal `npm ci`, lint, typecheck, 9 unit tests, and build pass.
- [x] Playwright: 15 passed, 11 intentional cross-device skips.
- [x] Production dependency audit: `npm audit --omit=dev` reports zero
  vulnerabilities; the full development tree reports five moderate findings.
- [x] Ruff, Ruff format, mypy, and documentation checks pass.
- [x] Clean-checkout matrix: the complete documented command set passes from an
  isolated tracked/non-ignored source copy with no cloud credentials.

## Final release gate

- [x] All four workflows execute durable end-to-end mutation paths.
- [x] Every local `PR-*` control passes without strict xfails.
- [x] No route may acknowledge a claimed event without performing or explicitly
  persisting the intended guarded workflow action.
- [!] Production smoke, rollback, Firebase browser auth, backup/restore,
  observability, and IAM evidence require a real staging environment.
- [!] A configured live Gemini eval requires a valid model credential and
  working billing/quota route.
- [!] Human security, safety, scope, and launch review remains required.
