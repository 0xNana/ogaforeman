# Implementation Status

## Status date

2026-08-14

## Summary

Conversational Operations phases 11–15 are implemented locally. OG now returns cited read-only
project advice, retains bounded per-user/project references that are revalidated against persisted
truth, and exposes typed conversation/advice/proposal/workflow responses in the global responsive
Ask OG drawer while reusing the existing multimodal Golden intake. Significant conversational
change requests and confirmation pauses are replay-safe ActivityEvents, and conversational task,
material, and issue commands surface optimistic conflicts instead of overwriting newer state.

The Daily Site Update vertical slice is implemented locally through the
authenticated API, persisted event/run state, ADK execution bridge, typed
mutation services, Firestore, source-linked reports, approvals, and activity
projection. Verified audio and image attachments are now read from durable
private storage by the claimed worker: Gemini transcription is persisted on the
source `SiteUpdate`, and image bytes plus project context enter structured
interpretation before existing policy and mutation routing. The repository also
includes release tooling, a Next.js product UI,
Firebase Auth emulator browser journeys, deployment scripts, observability
controls, and recovery utilities.

The browser E2E backend now invokes the canonical event worker instead of a
phrase-matching state simulator. Its deterministic interpreter replaces Gemini only
at the model boundary; Firestore holds workflow state, and production coordinator,
fact routing, mutation, approval, outbox, continuation, and supplier-action code
drives the journey from submission through the original run's completion.

Durability is now an enforced CI gate rather than optional local evidence. The
backend job starts Firestore and Storage emulators, runs all marked backing-service
tests with no skips, and separately runs the remaining suite without leaking
emulator environment into configuration tests. The multimodal restart case persists
both attachment metadata and real media objects, reconstructs service clients before
approval and continuation, and completes the original run exactly once.

Natural-language blocker facts now enter that same durable path. After entity
resolution, Oga blocks the matched task, traverses actual task `dependency_ids`,
creates a distinct downstream delay-risk issue, and projects both facts into the
daily report. The concise impact and pending schedule review persist on the same
`AgentRun`, are returned by the run API, and appear in the site-update receipt.

Blocker handling now performs the operational follow-through as well. A typed task
mutation verifies the blocker, source update, and blocked task together, creates one
`TaskSource.SITE_UPDATE` follow-up, inherits the blocked task's canonical assignee,
and atomically logs `task.follow_up_created`. The task survives fresh Firestore
clients and is visible from persisted snapshot state in Tasks and Needs You. The
mixed workflow still calculates 30 missing cement bags from recorded stock and
upcoming requirement, creates the request/approval, and pauses the original run.

Approval continuation now closes the remaining lifecycle gap. The voice-only
canonical scenario is observed while `SiteUpdate` is `PROCESSING` and its original
`AgentRun` is `RUNNING`, then reloaded in the durable approval wait through fresh
clients. Approval resolution leaves the run paused until its outbox event is claimed;
that continuation validates the persisted decision and resolver, resumes the exact
source run, submits once, and atomically logs resume and completion. Rejection is a
separate restart case: notes persist, the request is cancelled, the original run is
terminalized and audited, and no supplier action is queued or executed.

Workflow auditability now reconstructs that vertical slice without relying on raw
reasoning or browser state. Existing atomic mutation activities remain unchanged;
typed semantic events record media processing, authorized context retrieval,
validated interpretation counts, blocker/material/schedule decisions, report update,
approval pause, resume, supplier-simulator execution, and terminal outcome. Every
event is replay-safe and run/source linked, while an allowlist prevents prompts,
transcripts, raw media, signed URLs, credentials, or hidden reasoning from entering
the semantic metadata. `AgentRun.updated_at` advances with every transition and the
authorized API exposes the full lifecycle/trace/error contract.

This is still a **release candidate under construction**, not a deployable
public beta. Every coordinator event route now executes deterministic persisted
behavior before its claim is completed, including terminal approved-material
continuation. All currently identified non-cloud implementation blockers are
resolved; remaining gates require deployed auth/operations evidence, a
configured model, or human release review. The canonical evidence checklist is
[tasks/todo-v1.md](../tasks/todo-v1.md).

## Local verification history

Conversational phases 11–15 verification on 2026-08-14:

- focused advice, memory, API, audit, conflict, and drawer tests: passed
- Ruff check/format and mypy: passed
- backend without backing services: 413 passed, 24 deselected
- frontend Vitest: 48 passed
- frontend typecheck, lint, and production build: passed
- canonical mobile Golden Scenario: 7 passed

- uv locked sync: passed
- Ruff check and format: passed
- Mypy app: passed
- Backend without backing services: 305 passed, 23 deselected
- Firestore/Storage backing-service gate: 23 passed, no skips
- P0.1 focused multimodal suite: 79 passed, 1 Firestore test skipped in the
  clean run and then passed separately against `127.0.0.1:8085`
- Full Firestore emulator integration: 92 passed
- Firestore repository contract: 8 passed
- Routed workflow Firestore restart: passed
- Production readiness: 13 passed, no xfails
- Fixture eval: 8/8 cases and mutation diffs passed
- Deliberate regression eval: forbidden mutation detected as expected
- Capacity baseline: 5/5 scenarios passed
- Dry demo rehearsal: 3/3 runs passed
- P0.2 Firestore-backed worker/attachment proof: 2 focused tests passed
- P0.4 production-worker blocker/dependency proof: passed, including direct,
  transitive, and unrelated task assertions
- P0.5 production-worker follow-up/replay proof: passed; the full backing-service
  gate and focused mobile approval/resume journey also pass
- P0.6 voice approval/rejection restart matrix: 2 passed against fresh Firestore and
  Storage clients; the focused six-case mobile intake suite also passes
- P0.7 semantic audit timeline: required success/rejection events persist across
  fresh clients, remain single under replay, and carry no raw voice/model content
- Frontend install, checks, and build: passed with 15 unit tests
- Playwright desktop/mobile: 18 passed, 14 intentional device skips
- Production npm audit: zero vulnerabilities
- Documentation links/tests: passed
- Isolated clean-checkout command matrix: passed
- Deployed browser CORS: both Firebase Hosting origins pass API and private
  media-bucket preflight; an unconfigured origin receives no allow-origin header

Firestore auth bootstrap now converges through atomic document creation rather
than a contended read/write transaction. Its bounded create retry includes
Firestore's retryable `ABORTED` lock-timeout response, while `AlreadyExists`
still converges on the canonical user. The 32-call concurrency race and complete
backing-service suite pass. Frontend CI now installs Java 21 before Playwright
starts the Firestore emulator, matching the backend durability job.

The deployed API already allowed both Firebase Hosting origins. The direct media
bucket had no CORS policy, which blocked signed browser uploads before object
authorization could be evaluated. The bucket now uses the same two exact HTTPS
origins, allows the signed `PUT` contract headers, and denies an unconfigured
origin. `infra/deploy.sh` regenerates this policy from `CORS_ALLOWED_ORIGINS` on
every deployment.

The Playwright stack is self-contained and starts Firebase Auth emulator plus a
local API. Deployed Firebase sign-up and API bootstrap are now confirmed. The
staging worker is configured for live Gemini and completes events without model
errors, but post-setup live mutation quality evidence is not yet claimed.

On 2026-08-09 the deployed Firebase sign-up/bootstrap flow was confirmed by the
operator. The first live site-update attempts exposed an onboarding gap: new
projects had no supported way to establish the canonical task and material
context required by safe entity resolution. Authorized, idempotent task and
material setup APIs and UI forms now cover that path locally and await redeploy.

P0.1 now connects those durable browser uploads to the production worker path.
Voice bytes are checksum/size validated, sent to the configured Gemini audio
request, and persisted as one audited transcript enrichment before fact
extraction. Photo bytes and bounded authorized task/material context are included
in the structured Gemini request. A deterministic policy backstop prevents a
photo-only claim from completing work without corroboration and persists a
clarification wait instead. Failure/retry tests prove the same site update is
reused and an already-persisted transcript is not regenerated. SDK request tests
verify exact inline media bytes and MIME types; a live billable Gemini request was
attempted and reached Gemini, but the configured AI Studio project returned
`429 RESOURCE_EXHAUSTED` because its prepayment credits are depleted.

P0.2 removes the former browser-only workflow state machine. Local event delivery
calls the same worker entry point as production, then the same coordinator,
interpreter contract, fact router, mutation services, approval service, outbox
claim, continuation workflow, and external-action guard. The main mobile journey
observes a real purchase approval in Firestore, approves it through the product,
and verifies that the original run completes after exactly one supplier submission.
Voice and photo use the signed attachment contract and durable bytes; photo-only
completion evidence reaches the real clarification policy. A PDF-only submission
proves a recoverable failed run without a magic input phrase. During this migration,
Firestore execution exposed and fixed a read-after-write transaction ordering bug
in atomic attachment/activity persistence.

P0.3 moves restart evidence onto real local backing services. The canonical
multimodal test writes audio and photo objects through the Cloud Storage client,
processes the update through the production worker, and then uses fresh Firestore
and Storage clients to verify the site update, linked attachments, transcript, task,
issues, material ledger, request, pending approval, waiting run, report, processed
event, and activities. Approval is resolved after that restart; a second fresh
Firestore client processes the continuation and a third verifies the same run is
complete, the supplier action occurred once, and both original media objects remain
checksum-valid. CI uses the checked-in Firebase CLI and Java 21 to start both
emulators before running the marked gate.

P0.4 connects `IssueFact(BLOCKER)` to the existing schedule-impact calculation.
The blocker task is resolved from authorized project context and moved to `blocked`;
only graph-supported downstream tasks receive a separate `DELAY_RISK` issue. The
canonical seed now records plastering's electrical dependency, so the demo exposes
electrical schedule impact and cement shortage as distinct causes. Issue creation,
task state, report projection, and the run response are replay-safe and audited by
the existing typed mutation/lifecycle services.

P0.5 closes the gap between detecting a blocker and creating work to resolve it.
The worker now creates one deterministic follow-up task after the blocker transition,
links it to the source update, blocker issue, and blocked task, and carries forward
the blocked task's canonical assignee when present. Creation and activity commit
atomically and replay returns the existing task even if the source task is later
reassigned. Snapshot projections mark the active follow-up for Tasks and Needs You;
the canonical Firestore restart and mobile browser paths verify persistence and
visibility before the existing material approval resumes the same run.

P0.6 makes that approval boundary a fully audited state machine. The decision
transaction persists the approval and request status without invoking the supplier.
The continuation then derives the original run from the request source, verifies the
persisted decision/resolver, and records `agent_run.resumed` before the guarded
supplier action and `agent_run.completed` afterward. The rejection continuation uses
the same source lookup and records `agent_run.rejected`; forged pending decisions or
resolver mismatches are rejected, decision notes survive restart, and no supplier
outbox/activity exists on that branch.

P0.7 adds the user/debugger-facing causality between those durable mutations. A
typed action registry and allowlisted workflow-audit service record only observable
inputs, outputs, IDs, statuses, quantities, and reason codes. Semantic events paired
with a domain mutation commit in the same Firestore transaction; Firestore emulator
coverage specifically verifies all audit reads occur before writes. Approval
decisions inherit the linked run causality, external execution records the guarded
supplier adapter outcome, and legacy run documents receive a stable `updated_at`
fallback derived from their persisted lifecycle timestamps.

## Confirmed implementation

- Production code has no _PROJECT_DB or datetime.utcnow() dependency.
- Firestore transactions preserve project partitions, optimistic versions, and
  cached read versions for cross-collection mutation sets.
- Task, issue, material, request, report, attachment, approval, run, and activity
  state are durably projected by the canonical Daily Site Update path.
- Task-linked blockers create one authorized, idempotent, audited follow-up task
  with persisted site-update/issue/task sources and canonical assignee inheritance.
- Audio transcription is a durable, idempotent `SiteUpdate` enrichment with an
  atomic `site_update.transcribed` activity; the original attachment remains
  linked and replay skips already-transcribed audio.
- Image evidence reaches the configured interpreter with authorized project
  context and remains subject to confidence, clarification, entity-resolution,
  and typed-mutation policy.
- Task-completed, material-low/requested, blocker, overdue, delivery-delay, and
  daily-brief events now create deterministic runs and typed replay-safe domain
  mutations before the worker completes their event claims.
- Supplier submission is audited before delayed delivery can be emitted; delay
  processing updates the request, creates a risk, queues one notification, and
  completes the resumed material run after replay-safe continuation.
- Scheduled daily briefs atomically upsert the report, activity, and notification
  outbox record and survive a Firestore client restart.
- Scheduler HTTP dispatch is exercised through the real Pub/Sub worker endpoint
  and proves duplicate-safe report, activity, processed-event, and run state.
- Mutations enforce project authorization, idempotency, source context, and
  atomic activity emission.
- Project administrators can create canonical tasks and materials through
  `/api/v1`; setup writes atomically emit activities and tolerate same-key replay.
- Approval decisions expose optimistic stale conflicts through the API and UI.
- Checked-in Playwright covers command-center/activity desktop and mobile views,
  resource projections, approval/rejection persistence, stale conflicts,
  overflow, WCAG 2 AA scans, and mobile text/voice/photo intake with denial,
  invalid-upload, clarification, processing, and failure states.
- Browser workflow tests do not intercept run or approval requests. Deterministic
  E2E adapters replace external model, storage, and transport dependencies while
  production code exclusively owns persisted workflow state and transitions.
- The browser attachment path uses the production sign, private upload, verify,
  link, and run-status contracts rather than a direct demo upload endpoint.
- Authenticated frontend routes contain no project fixture snapshot or demo API;
  missing API configuration fails closed. The public `/demo` page remains a
  static marketing illustration and never reads or writes project state.
- CI installs locked dependencies, runs backend/frontend checks and Playwright,
  builds the container, and executes the non-root API/worker container smoke.

## Open implementation blockers

No known non-cloud implementation blockers remain in the canonical V1 scope.
Production cleanup removed the runtime frontend project fixture API and stray
untracked Gemini/Pub/Sub diagnostic scripts. Emulator-only seed/reset and fake
adapters remain solely as guarded verification infrastructure. Authenticated
reports now render the API-backed project identity instead of the canonical demo
project label, with a production-readiness regression guard.

## UI/UX overhaul state

- UI Phases 0–12 are complete; Phase 13 Golden Scenario acceptance is next.
- The authenticated shell now uses OG Foreman branding, the locked construction
  module navigation, project search/selection, persistent Ask OG, and responsive
  desktop/mobile navigation.
- All locked construction modules now have project-backed screens; Phase 1
  introduced no client-side demo records or backend contract changes.
- Phase 2 replaces the card dashboard with projection-backed project metrics,
  a prioritized attention list, today register, task lookahead, and derived OG
  notice. Missing schedule facts are labelled rather than fabricated.
- Phase 2 verification: 18 unit tests and 18 Playwright journeys pass, including
  desktop axe WCAG A/AA and mobile overflow checks.
- Phase 3 delivers searchable Tasks, Issues, and Materials registers with a
  shared accessible detail drawer. The snapshot now projects viewer-aware task
  fields, first-class issues, and material-request lifecycle records without
  adding workflows or mutations. Missing domain fields remain labelled.
- Phase 3 verification: 22 frontend unit tests, 307 Python tests, production
  build, 18 Playwright journeys, register axe, and mobile overflow pass.
- Phase 4 delivers task-backed List and Gantt schedule views with search,
  operational filters, milestones, dependency risk, downstream impact, and
  explicit unscheduled work. Milestones are persisted explicitly rather than
  inferred from duration; no new schedule-specific mutation was added.
- Phase 4 verification: 24 frontend unit tests, 307 Python tests, production
  build, 18 Playwright journeys, schedule axe, and mobile Gantt overflow pass.
- Phase 5 delivers a historical, searchable Daily Logs register from persisted
  reports. It renders the full client-ready record structure, labels missing
  crew/weather facts, preserves source-update provenance, and provides guarded
  metadata editing plus browser-native share and print export actions.
- Phase 5 verification: 26 frontend unit tests, 308 Python tests, production
  build, applicable Playwright journeys, Daily Log axe, and mobile overflow pass.
- Phase 6 replaces Photos and Documents placeholders with verified-attachment
  registers. Photo filters cover date, location, task, and uploader; authorized
  previews expose source-update, task, issue, and daily-log relationships. The
  document table retains familiar metadata without document-management sprawl.
- Phase 6 verification: 29 frontend unit tests, 309 Python tests, production
  build, applicable Playwright journeys, photo-detail axe, and mobile overflow pass.
- Phase 7 makes Ask OG a persistent, project-scoped interaction layer: a desktop
  right drawer and mobile full-screen sheet reuse the production site-update
  workflow for text, voice, photos, and files. Operational receipts distinguish
  persisted changes, OG-handled follow-through, and manager decisions.
- Phase 7 verification: 31 frontend unit tests, 309 Python tests, production
  build, 18 applicable Playwright journeys, drawer axe, focus containment, and
  mobile full-screen/overflow checks pass.
- Phase 8 delivers one continuous, date-grouped Activity audit stream with All,
  OG, Tasks, Issues, Materials, Approvals, Reports, and People filters. Every
  supported event links to its canonical project record, while the projection
  excludes event metadata and private model reasoning. The Golden Scenario test
  verifies task completion, blocker detection, material/approval transitions,
  daily-report updates, and the approved external action directly in Activity.
- Phase 8 verification: 33 frontend unit tests, 309 Python tests, production
  build, and 18 applicable Playwright journeys pass; Activity axe reports no
  WCAG A/AA violations and mobile overflow checks pass.
- Phase 9 makes each consequential proposal readable before a decision: action,
  quantity, affected work, needed date, and OG's evidence-based reason are visually
  separated. Approve/reject still use the authenticated version-checked service;
  terminal receipts now show the persisted resolver/time, and stale conflicts lock
  only their request until an explicit refresh confirms server truth.
- Phase 9 verification: 35 frontend unit tests, 309 Python tests, production build,
  and 18 applicable Playwright journeys pass; approval axe reports no WCAG A/AA
  violations. `npm audit --audit-level=high` reports no high or critical findings;
  five moderate findings remain in the Firebase CLI development dependency chain.
- Phase 10 replaces the compressed desktop overview on field viewports with a
  dedicated mobile home: project/date, concise blockers/material/decision attention,
  a large Talk to OG action, rapid photo entry, and completed/in-progress work.
  Both field actions open the existing full-screen authenticated composer, while
  Home, Tasks, OG, Photos, and More remain fixed one-handed navigation targets.
- Phase 10 verification: 36 frontend unit tests, 309 Python tests, production build,
  and 18 applicable Playwright journeys pass. Mobile field-home axe and overflow
  checks pass, and the Golden Scenario starts from Talk to OG without entering a
  desktop-style management screen.
- Phase 11 replaces accidental blank and skeleton-only screens with narrated loading,
  specific project recovery, true-empty module guidance, and report first-use states.
  A failed post-persistence intake now identifies that the original is saved, keeps
  the user's text and attachment visible, and reuses the same idempotency key on retry.
- Phase 11 verification: 39 frontend unit tests, frontend lint and typecheck, production
  build, and 19 targeted site-update/production-control tests pass; one emulator-only
  restart control remains skipped because `FIRESTORE_EMULATOR_HOST` is not configured.
- Phase 12 resolves the remaining visual-system token drift, keeps operational row
  headers distinct from column headers, and gives the mobile More sheet the same
  Escape, focus containment, scroll lock, and trigger-focus restoration guarantees
  as the OG and record drawers.
- Phase 12 verification: 40 frontend unit tests, lint, typecheck, production build,
  and all 18 applicable Playwright journeys pass. Axe reports no WCAG A/AA violations
  across the tested desktop and mobile surfaces, mobile overflow checks pass, and
  `npm audit --audit-level=high` reports no high or critical findings. Five moderate
  advisories remain confined to the Firebase CLI development dependency chain.

## Conversational operations

- Phases 0–9 are complete locally as of 2026-08-14.
- The router is typed and non-mutating; low-confidence actions and context-free confirmations
  stop at clarification, while site updates retain the existing Golden workflow destination.
- Phase 2 adds permission-aware, query-shaped typed projections for all documented context
  domains and corrects the Golden context's empty issue/approval projections.
- Phase 3 adds concise deterministic replies grounded in the authorized context snapshot, honest
  empty states, and a guard that preserves operational workflow ownership.
- Phase 4 adds typed project-scoped resolution for seven entity kinds, canonical aliases,
  revalidated context, strict fuzzy matching, and non-actionable ambiguity/unknown results.
- Phase 5 routes safe task creation and updates through typed Task services with project/member
  revalidation, atomic activity, idempotent replay, and negation/ambiguity completion guards.
- Phase 5 verification: 13 focused tests, Ruff, mypy, 370 non-backing backend tests, and all 7
  canonical mobile Golden Scenario journeys pass.
- Phase 6 routes safe material setup, stock counts, requirements, deliveries, and notes through
  typed services with append-only ledger, cumulative delivery, authorization, and replay guards.
- Phase 6 verification: 12 focused unit tests, 3 Firestore emulator tests, Ruff, mypy, 377
  non-backing backend tests, and all 7 canonical mobile Golden Scenario journeys pass. Phase 7
  safe issue operations is active.
- Phase 7 adds evidence-gated, project-scoped creation, assignment, status, resolution, and notes
  through the typed Issue service.
- Phase 8 adds explicit testable policy for routine, confirmation, approval, and deny/escalate
  mutations.
- Phase 9 adds dependency-aware, confirm-first schedule proposals and atomic downstream date
  shifts.
- Phase 10 routes conversational text through the existing durable site-update intake and Golden
  workflow. Phase 11 advice mode is active.

## Phase 8 state

| Work item | Evidence state |
| --- | --- |
| R-01 | Complete locally: 13 readiness controls pass without xfails |
| R-02 | Fixture gate passes; billed Vertex Gemini ran live but failed the canonical mutation/entity threshold (3/8 cases) |
| R-03 | Post-redeploy health, metrics, log correlation, sampled Cloud Trace metadata, and five policies pass; alert delivery is blocked by zero notification channels |
| R-04 | Firestore restore, Storage generation recovery, and managed backup visibility pass with four READY backups |
| L-01 | Commit `e168074` is deployed to API/worker/web; authenticated workflow runner is configured but operator `signBlob` IAM is missing |
| L-02 | Three-run deterministic four-workflow rehearsal passes; live Gemini reached the production worker, while configured eval/review remains open |
| L-03 | Complete locally: isolated locked install, test, build, browser, eval, demo, capacity, and docs matrix passes |

## External release gates

- Grant the staging smoke operator narrowly scoped service-account token signing,
  then verify authenticated project, site-update, agent-run, report, and activity journeys.
- Attach an approved Monitoring notification channel, trigger a controlled
  staging incident, confirm receipt, and record projection rebuild timing.
- Redesign the live eval boundary so Gemini extracts facts while deterministic
  code owns canonical IDs and mutation tokens, then rerun the billed Vertex gate.
- Complete human security, safety, scope, and launch review.

## Release position

Do not mark V1 production-ready until all four workflows execute durable,
idempotent mutation paths and the external evidence in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) is attached.
