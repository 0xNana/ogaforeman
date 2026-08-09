# Implementation Status

## Status date

2026-08-09

## Summary

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

This is still a **release candidate under construction**, not a deployable
public beta. Every coordinator event route now executes deterministic persisted
behavior before its claim is completed, including terminal approved-material
continuation. All currently identified non-cloud implementation blockers are
resolved; remaining gates require deployed auth/operations evidence, a
configured model, or human release review. The canonical evidence checklist is
[tasks/todo-v1.md](../tasks/todo-v1.md).

## Locally verified on 2026-08-09

- uv locked sync: passed
- Ruff check and format: passed
- Mypy app: passed
- Backend pytest: 281 passed, 19 emulator-dependent skipped
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
- Frontend install, checks, and build: passed with 10 unit tests
- Playwright desktop/mobile: 17 passed, 13 intentional device skips
- Production npm audit: zero vulnerabilities
- Documentation links/tests: passed
- Isolated clean-checkout command matrix: passed

Firestore auth bootstrap now converges through atomic document creation rather
than a contended read/write transaction. A 32-call concurrency race, three
additional isolated repeats, and the complete emulator integration suite pass.

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

## Confirmed implementation

- Production code has no _PROJECT_DB or datetime.utcnow() dependency.
- Firestore transactions preserve project partitions, optimistic versions, and
  cached read versions for cross-collection mutation sets.
- Task, issue, material, request, report, attachment, approval, run, and activity
  state are durably projected by the canonical Daily Site Update path.
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
- Production API configuration fails closed; deterministic frontend data is
  isolated behind explicit demo mode.
- CI installs locked dependencies, runs backend/frontend checks and Playwright,
  builds the container, and executes the non-root API/worker container smoke.

## Open implementation blockers

No known non-cloud implementation blockers remain in the canonical V1 scope.

## Phase 8 state

| Work item | Evidence state |
| --- | --- |
| R-01 | Complete locally: 13 readiness controls pass without xfails |
| R-02 | Local gates complete: fixture thresholds pass and a deliberate regression is rejected; configured Gemini remains external |
| R-03 | Staging health, metrics, log correlation, and five policies pass; Cloud Trace span and alert delivery remain |
| R-04 | Isolated Firestore export/import and Storage generation recovery pass; first managed backup remains pending |
| L-01 | Staging deploy, IAM, Scheduler, rollback, and Firebase sign-up/bootstrap pass; post-redeploy authenticated workflow smoke remains |
| L-02 | Three-run deterministic four-workflow rehearsal passes; live-model rehearsal absent |
| L-03 | Complete locally: isolated locked install, test, build, browser, eval, demo, capacity, and docs matrix passes |

## External release gates

- Redeploy the canonical-resource setup slice, then verify authenticated task,
  material, site-update, agent-run, report, and activity journeys in staging.
- Record a Cloud Trace span, alert delivery, first managed-backup visibility,
  projection rebuild timing, and production smoke.
- Run the configured Gemini eval with a valid key or billed Gemini Enterprise project and
  review mutation diffs before changing model/prompt configuration.
- Complete human security, safety, scope, and launch review.

## Release position

Do not mark V1 production-ready until all four workflows execute durable,
idempotent mutation paths and the external evidence in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) is attached.
