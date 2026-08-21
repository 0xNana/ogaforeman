# Implementation Status

## Status date

2026-08-21

## Summary

Conversational Operations phases 11–17 are implemented locally. OG now returns cited read-only
project advice, retains bounded per-user/project references that are revalidated against persisted
truth, and exposes typed conversation/advice/proposal/workflow responses in the global responsive
Ask OG drawer while reusing the existing multimodal Golden intake. Significant conversational
change requests and confirmation pauses are replay-safe ActivityEvents, and conversational task,
material, and issue commands surface optimistic conflicts instead of overwriting newer state.
The versioned conversational benchmark covers all 18 required categories, locks every release
threshold at 100%, and includes independent negative controls for mutation, approval, permission,
replay, conflict, memory, and audit failures. Its fixture result is evaluator evidence rather than
runtime-conformance evidence; Phase 17 adds a separate production-pipeline runtime gate.
The final Phase 1–16 audit also aligned mutation-policy permissions and bound schedule confirmation
to signed actor/project/versioned proposals. Phase 17 composes and dispatches typed routine
mutations, persists exact signed confirmation commands behind server-issued IDs, reuses existing
purchase/schedule approvals, and proves confirmation through Firestore restart and browser reload.
The OG drawer and mobile `Talk to OG` action now use one universal multimodal composer. Text,
voice, photo, and attachment submissions enter the same conversational API; intent routing decides
whether to answer, advise, mutate, confirm, or invoke the existing Golden site-update workflow.
The frontend has no competing conversational/site-update form or duplicate upload/send path.
The conversational UX correction adds authenticated product-help routing that bypasses project
authorization, memory, storage, and Gemini; a user-scoped entry point makes the no-project setup
response reachable; and cancelled tasks are excluded from persisted readiness counts. Deterministic
guards match only complete help/setup questions, so mutation-shaped messages still reach the model.
Setup/readiness answers remain persisted and authorized, unknown intent recovers conversationally,
and the API exposes an explicit `OG` assistant identity. Internal routing labels are no longer rendered as authors in the
conversation transcript. The locked conversational evaluation now includes the HELP category.

The ADK execution-authority migration is active. Resumable ADK applications now
persist session/invocation identity, non-site events enter ADK Runner workflows,
and conversational project actions use an ADK Runner around the existing typed
services. Approval continuation wiring is in progress; legacy projections and
deterministic services remain during the migration gate.

Project Initialization is **partially implemented**, not production-complete.
The earlier phase-level completion language is superseded by the audited gaps and
ordered gates in [`PROJ_INIT_IMPLE.md`](PROJ_INIT_IMPLE.md). PI-00 corrected the
test baseline; PI-01 preserves internally invalid drafts as typed validation
failures and blocks every persisted conflict at both confirmation boundaries;
and PI-02 enforces the complete durable lifecycle with safe, exact-claim restart
recovery. PI-03 makes canonical import provenance complete, derives trusted
source metadata from persisted project sources, and exposes tenant-authorized
explanation lookups. PI-04 blocks canonical duplicate/change/ambiguity conflicts
before review and reruns its additive-only preflight inside the commit transaction.
PI-05 makes validation and commit consume the same immutable exact mutation plan,
blocks oversized transaction/document plans while preserving their reviews, and
corrects canonical creation-activity identity and provenance metadata. The
canonical-import backend checkpoint is complete. PI-06 adds the dedicated New
Project wizard, complete project fields, explicit import-or-empty setup choice,
stable creation replay, and the project-scoped setup handoff. PI-07 adds typed
structured-source creation, paste and local text/Markdown entry, a reload-stable
import claim, and latest-nonterminal recovery through a source-safe bounded API.
Unsupported source adapters are rejected before extraction. One strict expected
failure still covers task-incorrect shortage calculation. PI-08 completes the
review UI lifecycle, persists stable decision claims across reload and response
loss, recovers optimistic conflicts, refreshes imported project state before
routing, and returns cancellation to setup. PI-09 through PI-14
remain open.

Project Initialization Phase 1 has partial local implementation: strict, schema-versioned
Pydantic contracts cover import drafts, draft-only temporary references,
provenance, explicit dates and units, warnings, conflicts, and task-to-material
requirements. Extraction provenance accepts only temporary IDs and a residential
fixture validates without Gemini or persistence.
Project Initialization Phase 2 has partial local implementation: `ProjectImportValidator`
is the sole complete-draft validation owner and performs side-effect-free
reference, duplicate-ID, self-dependency, dependency-cycle, duplicate-edge, unit
compatibility, duplicate-requirement, completion-evidence, milestone-date, and
unresolved-reference validation before any canonical write. Invalid drafts retain
their full extracted content plus typed warnings and conflicts. Exact canonical,
provenance, ledger, activity, and import-state writes and conservative document
size are now validated from the immutable PI-05 commit plan.
Project Initialization Phase 3 has partial local implementation: confirmed drafts persist
separate `CONFIRMED` and `IMPORTING` claims, then commit
canonical phases, tasks, dependencies, materials, inventory ledger entries,
requirements, provenance, import state, and activity in one repository
transaction; persisted review records, server-owned confirmation timestamps,
safe retryable failures, and request-fingerprint claims resume exact requests
after restart while preventing bypasses and mismatched replays. Phase linkage,
milestones, material locations, and requirement confidence are retained.
Project Initialization Phase 4 has partial local implementation: pasted project sources are
stored as first-class records with SHA-256 checksums, durable text, creator,
status, replay protection, and required linkage before import commit.
Project Initialization Phase 5 has partial local implementation: the structured text adapter
accepts pasted/Markdown/OG-template variation, normalizes bounded source text,
preserves unresolved dates, and produces a checksum-stable extraction input.
Project Initialization Phase 6 has partial local implementation: a native resumable ADK
workflow exposes source receipt/loading, schema-constrained Gemini extraction,
schema validation, draft normalization, deterministic validation, and the
needs-review handoff. Import records persist the ADK session/invocation identity,
lease, attempt, and every lifecycle transition from upload through terminal
outcome. Dependency outages and extraction failures retain safe diagnostics and
exact failed/expired claims resume; canonical IDs and mutation authority remain
application-owned.
Project Initialization Phase 7 has partial local implementation: known unit aliases are
canonically normalized between extraction and draft validation, while task names
retain their displayed text and use conservative Unicode/case/punctuation keys
only for duplicate detection.
Project Initialization Phase 8 has partial local implementation: the authenticated review API
extracts durable drafts through ADK, exposes tasks/dependencies/materials/
requirements/warnings/conflicts/unresolved references, and keeps canonical
project records unchanged until explicit confirmation. Cancellation discards the
draft without mutating project truth; confirmation and cancellation use durable
idempotency claims, terminal stale-request conflicts, extractor-independent
reads, safe failure projections, restart recovery, and project-scope enforcement.
Persisted blocking conflicts are rejected by the API and direct import service
before canonical writes.
Project Initialization Phase 9 has partial local implementation: the authenticated import
review route makes the pending canonical records legible as a read-only summary,
tables/lists for tasks, dependencies, materials, and task-grouped requirements,
plus explicit warning and conflict items. It reconstructs active, validation,
extraction, review, commit-failure, cancelled, and imported states from the API.
A conflict disables initialization; cancel and confirm retain reload-stable
idempotency keys and the persisted review version, rapid duplicate decisions are
guarded, stale versions reload, and completed decisions route to refreshed project
state or setup. Richer in-place corrections remain V2 scope.
Project Initialization Phase 10 has partial local implementation: an active project can start
from its actual site position. Confirmed import tasks retain explicit planned,
in-progress, completed, or blocked status; completed work requires its supplied
actual completion date, and opening material balances create ledger state without
inventing historical task-completion or inventory events.
Project Initialization Phase 11 has partial local implementation: deterministic readiness is
derived from canonical project records as empty, partially configured, or
operational. Setup responses report task, dependency, material-requirement,
schedule, initial-state, and missing-requirement facts instead of an AI score.
Project Initialization Phase 12 has partial local implementation: conversational operational
queries against the newly imported model now fetch entity-specific material
requirements and downstream dependency impact, returning precise facts without
generic fallbacks.
Project Initialization Phase 13 has partial local implementation: Golden Operations
read `MaterialRequirement` records instead of hardcoded quantities, but currently
aggregate unrelated active-task requirements. Task-specific shortage calculation
remains open under PI-09.
Project Initialization Phase 14 has partial local implementation: conversational dependency reasoning
uses the data-driven canonical task graph for schedule impact, guaranteeing that removing
a dependency automatically prevents the system from claiming the downstream impact.
Project Initialization Phase 15 has partial local implementation: new materials reported during site
updates are dynamically auto-created as canonical Material entities when unit and
quantity data is sufficient, avoiding manual re-initialization.
Project Initialization Phase 16 has partial local implementation: project imports emit user-facing
activity events during extraction, review, initialization, and individual entity creation
(task, dependency, material, requirement) with canonical entity IDs/types while
preserving actor, source/import identity, and timestamps.
Project Initialization Phase 17 has partial local implementation:
`ProjectImportDiffService` compares authorized canonical phases, tasks/milestones,
dependencies, materials/aliases, and requirements. Normalized matches and ambiguous
or changed relationships persist as blocking review conflicts; only wholly new
entities are additive, and the guard reruns in the commit transaction. Full
changed/removed reconciliation remains deferred by V1 policy.

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

Native ADK migration Phase 16–19 verification on 2026-08-16:

- production-worker multimodal, conversation-routing, native workflow, and run-API
  correlation regressions: 11 passed
- Ruff checks for the ADK runtime, worker bridge, and run projection: passed
- live-cloud voice/photo execution remains a release gate requiring configured
  Gemini credentials and private media access

Project Initialization PI-02 verification on 2026-08-19:

- required workflow and review-API gate: 20 passed
- focused importer, validation, and review-API regressions: 39 passed, with only
  the PI-03 provenance, PI-04 duplicate-import, and PI-05 write-budget tests kept
  as strict expected failures
- fresh-client Firestore restart coverage: 2 passed for persisted draft
  validation and persisted import-claim commit recovery
- repository-wide Ruff check/format and focused PI-02 mypy: passed
- the unrelated `app/services/site_updates.py` assignment mismatch was fixed
  during PI-03; app-wide mypy now passes

Project Initialization PI-03 verification on 2026-08-19:

- trusted provenance covers phases, tasks, milestones, dependencies, materials,
  opening inventory ledger entries, and material requirements
- direct target, dependency-pair, and provenance-record API lookups resolve the
  trusted project/import/source context without exposing stored source content
- focused service/provenance/API verification: 21 passed, with only the PI-04
  duplicate-import regression retained as a strict expected failure
- Firestore persistence and authorization verification: 22 passed against the
  local emulator
- site-update regression verification after the typing-only variable fix: 10 passed
- repository-wide Ruff check/format and app-wide mypy (152 modules): passed

Project Initialization PI-04 verification on 2026-08-19:

- required deterministic diff and importer gate: 25 passed
- focused review, validation, and provenance regressions: 32 passed, with only
  the PI-05 write-budget guard retained as a strict expected failure
- fresh-client Firestore lifecycle and distinct-import duplicate gate: 3 passed
  against the local emulator
- exact replay, additive-only second import, normalized duplicate/change detection,
  persisted review conflicts, and commit-time concurrency recheck are covered
- dependency sync, repository-wide Ruff check/format, and app-wide mypy: passed
- the optional all-non-backing run was stopped in the known long-running capacity
  baseline; no completion claim is made for that broader command

Project Initialization PI-05 and backend-checkpoint verification on 2026-08-19:

- focused importer, validator, and review-API regression suite: 51 passed
- exact planned count equals writes attempted by the canonical transaction;
  dependency and creation activities use canonical target IDs/types and retain
  source/import metadata
- oversized drafts persist all 75 test tasks for review, transition to typed
  `VALIDATION_FAILED`, and return 422 on confirmation without canonical writes
- injected mid-commit collision transitions to retryable `IMPORT_FAILED` while
  rolling back every phase, provenance, material, ledger, requirement, and
  creation activity write
- Firestore repository atomicity plus fresh-client exact replay/restart gate:
  12 passed against the local emulator
- locked dependency sync, repository-wide Ruff check/format, app-wide mypy, and
  documentation validation: passed

Project Initialization PI-06 verification on 2026-08-19:

- required frontend project gate: 12 passed; ESLint and TypeScript passed
- complete create-project request validation and domain regressions: 15 passed
- Firestore onboarding, exact replay, one-activity, full-field persistence, and
  mismatched-claim rejection: 3 passed against the local emulator
- production-build Playwright lost-response retry journey: passed in desktop and
  mobile Chromium; the wizard has no WCAG A/AA violations in the scanned state
- `npm ci` completed from the lockfile; `npm audit --audit-level=high` reports no
  high or critical vulnerabilities (five moderate issues remain in the
  `firebase-tools` development dependency chain)

Project Initialization PI-07 verification on 2026-08-19:

- required frontend setup/import gate: 11 passed; ESLint and TypeScript passed
- focused review API and structured-source regression suite: 25 passed, including
  latest-active recovery beyond a page of terminal records and unsupported source
  rejection before persistence/extraction
- production-build Playwright response-loss recovery: passed in desktop and
  mobile Chromium with one import POST and no WCAG A/AA violations in the scanned
  setup state
- locked dependency sync, repository-wide Ruff check/format, app-wide mypy, and
  documentation validation: passed

Project Initialization PI-08 verification on 2026-08-21:

- required frontend review/setup gate: 26 passed; ESLint and TypeScript passed
- production-build Playwright decision/recovery gate: 4 passed across desktop and
  mobile Chromium, with mobile fixed at 360 px
- confirm and cancel both replay the same persisted decision after committed
  response loss; the refreshed snapshot contains one Excavation and one Foundation
  task after confirmation
- keyboard order passed and the review state had no WCAG A/AA violations in the
  desktop or 360 px scans

Project Initialization PI-01 verification on 2026-08-19:

- contract, deterministic-validation, and review-API gate: 24 passed, with the
  PI-02 extractor-outage and PI-05 exact-write-budget regressions still strict
  expected failures
- direct importer-service boundary: 9 passed, with the PI-03 provenance and
  PI-04 duplicate-import regressions still strict expected failures
- focused Ruff check/format and documentation validation: passed
- the later PI-03 verification fixed the unrelated site-update assignment mismatch
  and restored a passing app-wide mypy gate

Project Initialization Phase 8 verification on 2026-08-18:

- review API lifecycle, outage recovery, stale replay, authorization, and
  discard/confirm gates: 7 passed
- project initialization regression suite: 43 passed (39 unit/API, 4 workflow)
- Ruff check/format and app-wide mypy for review API, lifecycle services, importer,
  and ADK extraction bridge: passed
- exact-run approval-continuation E2E and the 100-project scheduler capacity
  baseline: passed; local SQLite ADK session services are disposed per delivery
  and guarded against concurrent single-writer contention
- production-readiness controls: 12 passed, 1 Firestore-emulator restart test
  skipped because `FIRESTORE_EMULATOR_HOST` is not configured locally

Project Initialization Phase 9 verification on 2026-08-18:

- frontend import API-boundary and review-component coverage: 12 passed
- full frontend unit suite: 54 passed across 18 files
- frontend TypeScript, ESLint, and production build: passed

Project Initialization Phase 10 verification on 2026-08-18:

- project-import service regression covers an active mid-project initialization,
  all initial task states, opening stock, completion dates, and the absence of
  fabricated historical activity.

Project Initialization Phase 11 verification on 2026-08-18:

- deterministic readiness unit tests and project-setup conversation integration
  coverage pass for empty, partially configured, and operational projects.

Project Initialization Phase 12 verification on 2026-08-18:

- conversational project context tests verify correct domains for 'need', 'require', 'after', and 'what happens'
- conversational responses tests ensure dependencies and material requirements correctly format into concise responses

Project Initialization Phase 13 verification on 2026-08-18:

- Golden scenario correctly computes material shortages using MaterialRequirement project state dynamically, replacing hardcoded fallback logic
- test suite confirms no regressions in site update workflows

Project Initialization Phase 14 verification on 2026-08-19:

- site update processor verified to extract delay risk strictly via canonical Task `dependency_ids`
- test suite confirms that removing a task dependency from the project context avoids logging downstream impact

Project Initialization Phase 15 verification on 2026-08-19:

- end-to-end integration test successfully injects unknown material updates and confirms new materialized tracking entities
- test suite confirms authorization bounds accurately delegate operational permission for runtime auto-creation

Project Initialization Phase 16 verification on 2026-08-19:

- test suite confirms project initialization generates the exact sequence of user-facing activity logs (`project.import.started`, `project.initialized`, `task.created`, etc.) without internal noise
- verification ensures correct entity_id mapping, timestamp preservation, and source references on each event

Project Initialization Phase 17 verification on 2026-08-19:

- test suite confirms `ProjectImportDiffService` interface is operational, correctly identifying draft tasks as `ADDED` structurally compared to the initialized `ProjectContext`

Conversational Phase 16 verification on 2026-08-14:

- category-complete conversational fixture eval: 18/18 passed at every locked threshold
- deliberate unsafe-mutation artifact: gate failed on `ambiguous_completion` as expected
- 13 isolated guard regressions: all detected by the release gate
- focused eval tests: 20 passed
- conversational eval Ruff check/format and mypy: passed

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
