# Oga Foreman V1 Evidence Audit

Audited 2026-08-09 against production paths, tests, artifacts, frontend journeys,
and deployment scripts. This file is the canonical checklist; the legacy
`tasks/todo.md` checklist is retired.

Legend: `[x]` implemented and verified locally; `[~]` partially implemented
or unstable; `[ ]` implementation/evidence missing; `[!]` blocked only on a
real cloud environment, live model credential/billing, or human release gate.

## ADK execution authority migration

## Project initialization

Overall status: **partial**. The checked implementation claims from the prior
phase sequence are reopened as partial evidence until
[`docs/PROJ_INIT_IMPLE.md`](../docs/PROJ_INIT_IMPLE.md) passes its production
gates. Strict expected-failure tests track audited defects without misreporting
them as passing behavior. PI-00 through PI-08 and the canonical-import backend
checkpoint are complete locally; the remaining strict expected failure tracks PI-09.

PI-06 routes every New Project action through one accessible, reload-safe wizard;
persists name, location, timezone, description, dates, and project status; and
records the import-or-empty setup choice in the project-scoped setup URL. The
caller-owned project creation claim survives reload and exact Firestore replay,
so a lost response cannot create a second project. PI-07 adds paste and local
`.txt`/`.md` source entry, a reload-stable import claim, bounded latest-active
recovery, and browser/server rejection of unsupported adapter types before model
invocation. PI-08 renders the complete review lifecycle, persists stable decision
claims across reload/response loss, recovers optimistic conflicts, and routes
imported/cancelled outcomes to refreshed overview/setup destinations.

- [~] Phase 0 domain audit documents the existing canonical model, persistence,
  authorization, ADK boundary, and the concepts that must be created or extended.
- [~] Phase 1 canonical import contracts validate a complete residential draft
  without Gemini, persistence, or arbitrary canonical IDs from extraction output.
- [~] Phase 2 deterministic validation rejects invalid references, duplicate or
  cyclic dependencies, and incompatible material units before canonical writes;
  unresolved references remain review warnings. PI-01 makes it the sole
  complete-draft validation owner and persists invalid drafts with typed blockers.
  PI-05 shares one immutable exact write plan with commit and blocks transaction
  or document limits without discarding the review draft.
- [~] Phase 3 deterministic importer requires a persisted review and explicit
  confirmation, generates canonical IDs, commits the canonical model plus
  provenance/activity/inventory records, preserves imported fields, records
  retryable failures, persists separate confirmation/import claims, resumes exact
  claims after restart, and rejects mismatched retries. PI-03 makes provenance
  complete for every imported fact, sources its trusted metadata from persisted
  project sources, and exposes tenant-authorized explanation lookups. PI-05
  verifies the prepared canonical/provenance/activity/import-state writes against
  the validated plan before atomic commit and proves failure rollback is partial-free.
- [~] Phase 4 persists first-class project sources with pasted text/checksum,
  durable metadata, creator/status, replay protection, and import linkage.
- [~] Phase 5 structured text adapter accepts pasted text, Markdown, and OG
  template variation and produces normalized source text for extraction without
  inventing dates or canonical entities.
- [~] Phase 6 native ADK extraction workflow persists a resumable node trace,
  session/invocation identity, extraction lease/attempt, and recoverable failure
  state from source receipt through schema-constrained Gemini extraction,
  normalization, deterministic validation, and needs-review handoff. PI-02 now
  persists and enforces every lifecycle transition and safely resumes exact
  expired/failed claims.
- [~] Phase 7 deterministically normalizes known Gemini unit aliases before
  canonical draft validation, and detects punctuation-only task-name duplicates
  without merging distinct activities.
- [~] Phase 8 exposes the review-first import API for extraction, review,
  confirmation, cancellation, and draft discard; canonical project truth remains
  unchanged until server-authoritative confirmation, with durable request claims,
  stale-replay conflicts, outage-safe reads/decisions, project-scope checks, and
  a bounded local SQLite ADK fallback that safely serializes concurrent writes;
  persisted conflicts block both API and direct-service confirmation, and
  dependency outages leave reloadable records with safe retry diagnostics.
- [~] Phase 9 presents each persisted import draft as a focused read-only review
  of its task, dependency, material, and task-grouped requirement records, with
  explicit warnings and conflict blockers before the version-checked cancel or
  confirm-and-initialize decision. PI-08 adds every active/failure/terminal state,
  reload-stable decision claims, duplicate-click suppression, stale-version
  recovery, refreshed completion routing, and 360 px/WCAG browser evidence;
  in-place editing remains V2 scope.
- [~] Phase 10 initializes an active, mid-project site from explicit task state
  (`planned`, `in_progress`, `completed`, or `blocked`) and opening material
  quantity without fabricating historical task or inventory events.
- [~] Phase 11 derives `empty`, `partially_configured`, and `operational`
  readiness entirely from canonical project records, exposing task, dependency,
  material, requirement, schedule, initial-state, and configuration-gap facts.
- [~] Phase 12 queries the newly imported model for operational context (e.g. material
  requirements, dependencies) using entity-specific project state without generic fallbacks.
- [~] Phase 13 connects imported requirements to Golden Operations rather than
  hardcoded quantities, but task-specific shortage selection remains open.
- [~] Phase 14 enforces data-driven schedule dependency reasoning. Blockers dynamically
  traverse actual canonical task dependencies rather than making hallucinated or hardcoded
  fallback impact claims.
- [~] Phase 15 supports material auto-creation during site operations. A valid material
  fact with sufficient naming and unit data creates a typed entity when it does not exist,
  without treating operations as a project re-import.
- [~] Phase 16 emits user-facing activity for project import lifecycle events and entity
  creations (`project.import.started`, `project.import.extracted`, `project.import.reviewed`,
  `project.initialized`, `task.created`, `dependency.created`, `material.created`,
  `material.requirement.created`), avoiding internal extraction spam while preserving audit
  fields (actor, source, import ID, and timestamp). PI-05 corrects each creation
  event's canonical entity type and dependency target identity.
- [~] Phase 17 provides deterministic, authorized canonical preflight through
  `ProjectImportDiffService`: normalized duplicate/change/ambiguous matches are
  persisted as review conflicts, only genuinely new entities remain additive,
  and the same guard reruns inside the commit transaction. Full reconciliation
  remains deferred by policy.

- [ ] P0 Approval continuation resumes the same durable ADK session and
  invocation after worker/container restart and completes the original run once.
- [ ] P1 Every non-site agentic event executes through ADK rather than
  `OgaCoordinator` or `RoutedEventExecutor`.
- [ ] P2 Conversational queries and actions execute through ADK Runner plus
  typed deterministic tools.
- [ ] P3 Registered `LlmAgent`s are wired to production use or removed, with no
  unused agents in architecture documents.
- [ ] P4 Legacy route-map authority, manual `AgentRun` workflow progression,
  and custom resume orchestration are removed; `AgentRun` is observable only.

## Conversational operations

- [x] C-01 Phase 0 audit documents the locked Golden Scenario, reusable architecture,
  extension boundaries, and duplicate-orchestration risks.
- [x] C-02 Phase 1 provides a typed intent taxonomy, structured Gemini classifier,
  deterministic eval boundary, contextual response guards, low-confidence mutation gate,
  and explicit routing of site updates to the existing Golden workflow.
- [x] C-03 Phase 2 retrieves authorized, query-relevant, bounded project context without
  mutation and fixes the Golden context's hard-coded issue/approval omissions.
- [x] C-04 Phase 3 formats grounded context into concise conversational responses, honest empty
  states, and rejects operational destinations that belong to existing workflows.
- [x] C-05 Phase 4 resolves all documented project entities, rejects cross-project/context-kind
  mismatches, and clarifies ambiguous references before mutation.
- [x] C-06 Phase 5 executes safe task operations through existing typed task services, with
  project/member revalidation, atomic activity, replay safety, and completion-language guards.
- [x] C-07 Phase 6 executes safe material operations through existing typed material services,
  append-only stock ledger entries, cumulative delivery receipts, and risk-workflow routing.
- [x] C-08 Phase 7 executes safe issue operations through typed issue services with evidence,
  membership, authorization, atomic activity, and replay guards.
- [x] C-09 Phase 8 classifies every conversational mutation with explicit deterministic policy and
  operation-specific authorization aligned with the typed mutation services.
- [x] C-10 Phase 9 proposes schedule changes with dependency impact and uses signed, version-bound
  confirmation tokens that reject altered or stale proposals.
- [x] C-11 Phase 10 routes chat/text site facts into the existing Golden intake workflow.
- [x] C-12 Phase 11 provides cited, grounded, non-mutating project advice.
- [x] C-13 Phase 12 persists bounded per-user/project conversational references, revalidates every
  remembered entity, and refuses client-asserted or raw-text confirmation state.
- [x] C-14 Phase 13 exposes typed conversation replies, advice, proposed changes, and Golden
  workflow handoffs through the responsive global Ask OG drawer.
- [x] C-15 Phase 14 records significant conversational requests and confirmation transitions as
  allowlisted, replay-safe activities while excluding private reasoning and casual chatter.
- [x] C-16 Phase 15 applies duplicate suppression and explicit stale-version conflicts to
  conversational task, material, and issue commands.
- [x] C-17 Phase 16 provides a versioned, category-complete conversational evaluation gate with
  deterministic release artifacts and negative controls for every safety-critical outcome.
- [x] C-18 Phase 17 connects the conversational API to typed mutations, durable signed proposals,
  existing purchase and schedule approvals, accessible drawer confirmation, runtime evals, and
  Firestore/browser restart proof.
- [x] C-19 The existing multimodal composer is the single OG input across drawer and mobile entry;
  all modalities use the conversational API and `SITE_UPDATE` preserves the Golden workflow.
- [x] C-20 Product help works without populated project state; project setup/readiness comes from
  authorized persisted state; assistant turns render as OG without exposing internal route labels;
  conversational and Golden Scenario regression gates pass.

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
- [x] G-07 New projects expose authorized, idempotent task and material setup
  APIs and UI forms, so safe agent entity resolution no longer depends on demo
  seed data; every setup mutation atomically emits an activity.
- [x] P0.1 Real multimodal intake retrieves checksum-verified durable audio/photo
  bytes in the claimed worker. Audio transcription persists atomically on the
  existing `SiteUpdate`; images plus authorized project context reach the Gemini
  request; retries reuse the update/transcript; visual-only completion waits for
  clarification; Firestore restart and replay coverage passes.
- [x] P0.2 The browser site-update backend no longer branches on literal phrases or
  writes run state itself. Text, voice, photo, approval, and continuation requests
  execute the production worker, coordinator, fact routing, typed mutations,
  approval service, outbox claim, original-run resume, and guarded supplier action
  against the Firestore emulator. Deterministic substitutes are confined to Gemini,
  object storage, and in-process event delivery boundaries.
- [x] P0.3 CI starts Firestore and Storage emulators and executes every registered
  `backing_services` test with no skips. The canonical multimodal test reconstructs
  Firestore and Cloud Storage clients around the approval pause, proves all workflow
  records plus original media bytes survive, and resumes the same run exactly once.
- [x] P0.4 Actionable blocker facts now block the resolved project task and traverse
  the persisted dependency graph to create a separate downstream delay-risk issue.
  The source task and supported dependents appear in the daily report and in a
  restart-safe `AgentRun` response; unrelated tasks are excluded without phrase rules.
- [x] P0.5 A task-linked blocker now creates one assigned, source-linked follow-up
  through the typed task service and atomically logs it. It is API-backed in Tasks
  and Needs You, survives Firestore restart, and duplicate event delivery cannot
  create another action. The same mixed workflow still calculates a 30-bag shortage,
  creates one request/approval, and pauses the original run before supplier action.
- [x] P0.6 The voice-only canonical workflow now proves its real processing and
  waiting states, reloads the same run after fresh Firestore/Storage clients, and
  atomically logs resume/reject/complete transitions. Approval submits once and
  completes that run; rejection preserves notes, cancels the request, and produces
  no supplier action. Both continuation events suppress duplicate delivery.
- [x] P0.7 Existing mutation activities are preserved and the production workflow
  now emits a typed, replay-safe semantic timeline for media, context, interpretation,
  blocker/material/schedule decisions, report update, approval pause, continuation,
  external execution, and terminal outcome. Metadata is allowlisted and excludes
  raw model/media data; the authorized AgentRun API exposes the complete lifecycle
  identity, attempt, trace, timestamp, checkpoint, and error contract.

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
- [!] Workload IAM plus Firestore and Storage readiness are deployed; Firebase
  browser tokens and authenticated cross-project API/media enforcement remain.

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
- [x] Voice/photo attachments are consumed as actual durable bytes by the
  application worker; this gate no longer relies on a client-supplied transcript
  or attachment metadata alone.
- [x] Duplicate replay and Firestore client restart are covered through the
  wired site-update worker path.

ADK migration Phase 16–19 release gates:

- [ ] Live deployed voice/photo execution with production Gemini and private
  media credentials is verified end to end.
- [x] Conversational site updates reuse the canonical intake and native ADK
  workflow path.
- [x] Agent-run projections expose authorized ADK correlation identifiers while
  keeping ADK events separate from domain ActivityEvents.
- [x] ADR-001 records the ADK orchestration boundary and supersession rule.

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
- [x] E-02 Scheduler HTTP dispatch feeds the real Pub/Sub worker push path; the
  deployed `europe-west1` job produced one durable report, activity, processed
  event, completed run, and outbox record, and a second dispatch changed no counts.

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
  test/eval boundaries. Authenticated frontend runtime code contains no project
  fixture snapshot or demo API fallback.

## UI/UX overhaul

- [x] UI Phase 0 audits and freezes the authenticated frontend architecture.
- [x] UI Phase 1 delivers the OG Foreman project shell, locked ten-module
  navigation, project selector/search, persistent Ask OG, responsive mobile
  navigation, honest projection-gap routes, and WCAG/browser evidence.
- [x] UI Phase 2 replaces the existing command center with the operational
  Overview defined in `docs/UI_UX_OVERHAUL.md`.
- [x] UI Phase 3 replaces Task and Material card/modal patterns and the Issues
  placeholder with searchable operational registers and accessible detail drawers.
- [x] UI Phase 4 replaces the Schedule placeholder with task-backed List and
  Gantt planning views, dependency risk, milestones, filters, and activity detail.
- [x] UI Phase 5 makes Daily Logs a first-class historical module with persisted
  report facts, source-update provenance, guarded edits, share, and print export.
- [x] UI Phase 6 projects verified attachments into filterable Photos and focused
  Documents registers with authorized previews and persisted record relationships.
- [x] UI Phase 7 makes Ask OG globally available as an accessible desktop drawer
  and mobile sheet backed by the durable multimodal site-update workflow.
- [x] UI Phase 8 replaces the activity table with a continuous, date-grouped audit
  stream, eight operational filters, canonical related-record links, and Golden
  Scenario browser evidence without projecting private model reasoning.
- [x] UI Phase 9 makes consequential approvals self-explanatory, persists proposal
  display context, records resolver/time receipts, and scopes stale-version recovery
  to the affected request without weakening authorization or version guards.
- [x] UI Phase 10 provides a dedicated one-handed field home with concise attention,
  large Talk to OG and photo actions, today status, fixed five-item navigation, and
  Golden Scenario submission through the full-screen mobile composer.
- [x] UI Phase 11 gives production screens deliberate loading, true-empty, filtered,
  recoverable error, and success states; saved intake failures retain the original
  update and retry through the same idempotency claim.
- [x] UI Phase 12 completes launch polish with consistent operational table styling,
  resolved design tokens, keyboard-contained mobile navigation, focus restoration,
  responsive browser coverage, and WCAG A/AA verification.

## Reliability and launch

- [x] R-01 `tests/production_readiness` maps PR-01 through PR-13 and reports
  13 passing controls with no xfails.
- [!] R-02 Fixture eval passes 8/8 thresholds and records per-case mutation
  diffs. The billed Vertex Gemini eval is configured and ran live, but passed
  only 3/8 because model-generated canonical mutation tokens diverge from the
  deterministic resolver contract; the gate correctly remains closed.
- [!] R-03 Post-redeploy liveness, readiness, metrics, exact log correlation,
  sampled Cloud Trace metadata, and five deployed alert policies pass. Alert
  delivery is blocked because the project has no notification channels.
- [x] R-04 Protected Storage, isolated Firestore export/import restore, historical
  object-generation recovery, and managed backup visibility pass. Four READY
  managed backups were visible on 2026-08-13.
- [!] L-01 Staging deployment, least-privilege workload IAM, public health smoke,
  real Scheduler dispatch, and explicit API/worker rollback rehearsal pass.
  Firebase sign-up/bootstrap passes. A dedicated authenticated smoke runner is
  configured, but its post-redeploy run is blocked by missing
  `iam.serviceAccounts.signBlob` permission for the operator.
- [!] L-02 Three deterministic dry runs and local browser/API/Firestore evidence
  pass, including terminal approved-material continuation; the configured live
  Gemini route still needs post-setup mutation evidence and review.
- [x] L-03 README/status/auth/deployment/operations/demo docs pass, and the
  isolated clean-checkout runner records locked backend/frontend installs,
  static checks, tests, builds, browser journeys, evals, demo, and capacity.
- [x] Production cleanup removes the frontend runtime project fixture API and
  hard-coded authenticated report identity, plus stray untracked Gemini/Pub/Sub
  diagnostic scripts. Guarded emulator seed/reset, deterministic eval fixtures,
  and test doubles remain verification-only.

## Latest local evidence

- [x] Backend without backing services: 305 passed, 23 explicitly deselected.
- [x] Durable backing services: 23 passed against Firestore and Storage emulators,
  with no skips.
- [x] P0.1 multimodal API/worker/storage/model-shape coverage: 79 passed, with
  the Firestore restart case also passing separately against `127.0.0.1:8085`.
- [!] P0.1 live Gemini audio smoke reached the configured API but returned
  `429 RESOURCE_EXHAUSTED` because AI Studio prepayment credits are depleted.
- [x] Production readiness: 13 passed, no xfails.
- [x] Firestore repository contract: 8 passed.
- [x] Routed workflow regression: memory scenarios plus Firestore client restart
  persistence pass, including terminal approved-material continuation.
- [x] Firestore emulator integration: 92 passed; the atomic auth bootstrap's
  32-call race also passes with bounded retry of transient emulator lock aborts.
- [x] Playwright CI installs Java 21 before launching its Firestore emulator;
  the full desktop/mobile suite passes with 17 tests and 13 device skips.
- [x] Deployed API and media-bucket CORS allow both exact Firebase Hosting
  origins; signed-upload preflight succeeds and an unconfigured origin receives
  no allow-origin header. Deployment reapplies the policy from configuration.
- [x] Fixture eval: 8/8 cases and mutation-diff thresholds passed.
- [x] Deliberate regression eval: the forbidden negated-task mutation is
  detected and recorded in `artifacts/evals/deliberate-regression.json`.
- [x] Local scheduler-to-worker proof: HTTP dispatch and Pub/Sub push produce
  one durable daily brief mutation set under duplicate delivery.
- [x] Capacity baseline: five scenarios passed.
- [x] Demo rehearsal: three dry runs passed, including approval, rejection,
  replay suppression, worker restart, and delivery delay.
- [x] P0.2 production-path browser/API proof: the duplicate-safe update pauses on
  one durable purchase approval, approval completes the same run through one
  claimed continuation, and the Firestore attachment transaction emits both audit
  records; 2 focused emulator tests pass.
- [x] P0.3 restart proof: site update, attachments and original bytes, transcript,
  tasks, issues, materials, approval, waiting/completed agent run, and activities
  survive fresh clients; post-restart approval continuation executes once.
- [x] P0.4 blocker-impact proof: generic natural-language absence resolves to the
  canonical blocked task, direct/transitive dependency risk excludes unrelated work,
  three distinct full-scenario issues survive backing-service restart, and the mobile
  receipt renders the persisted schedule summary and action.
- [x] P0.5 follow-through proof: the same production worker creates one canonical-
  assignee follow-up linked to the blocker/site update, logs it, survives restart,
  and renders it in Tasks and Needs You before the material approval resumes.
- [x] P0.6 pause/resume proof: actual stored voice bytes produce the complete
  canonical scenario; fresh clients observe `PROCESSING/RUNNING`, the durable wait,
  decision-without-execution, and separate approve/reject continuations. Approval
  resumes and completes the exact run with one supplier submission; rejection keeps
  its reason, terminalizes the run, and has zero supplier actions.
- [x] P0.7 audit proof: the same restart matrix persists the required semantic
  activities with the original run/source causality, rejects non-allowlisted workflow
  metadata, suppresses replay duplicates, and exposes stable `updated_at` plus the
  full public run contract.
- [x] Frontend: normal `npm ci`, lint, typecheck, 15 unit tests, and build pass.
- [x] Playwright: 18 passed, 14 intentional cross-device skips, including a real
  Firestore-backed approval/resume journey with no workflow request interception.
- [x] Production dependency audit: `npm audit --omit=dev` reports zero
  vulnerabilities; the full development tree reports five moderate findings.
- [x] Ruff, Ruff format, mypy, and documentation checks pass.
- [x] Clean-checkout matrix: the complete documented command set passes from an
  isolated tracked/non-ignored source copy with no cloud credentials.
- [x] Staging deployment: `ogaforeman-cloud-2026` runs API and private worker
  revisions in `europe-west1` from image tag `0aa4a2c8dc7e`.
- [x] Staging operations: health/metrics/log correlation, duplicate-safe
  Scheduler delivery, rollback traffic restoration, isolated Firestore restore,
  and Storage generation recovery are recorded under `artifacts/operations/`.

## Final release gate

- [x] All four workflows execute durable end-to-end mutation paths.
- [x] Every local `PR-*` control passes without strict xfails.
- [x] No route may acknowledge a claimed event without performing or explicitly
  persisting the intended guarded workflow action.
- [!] Staging deploy, rollback, Scheduler, IAM, log correlation, isolated restore,
  and Storage recovery evidence pass. Firebase browser auth, authenticated API
  smoke, first managed-backup visibility, Cloud Trace, and alert delivery remain.
- [!] A configured live Gemini eval requires a valid model credential and
  working billing/quota route.
- [!] Human security, safety, scope, and launch review remains required.
