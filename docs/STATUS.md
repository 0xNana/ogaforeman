# Implementation Status

## Status date

2026-08-09

## Summary

The Daily Site Update vertical slice is implemented locally through the
authenticated API, persisted event/run state, ADK execution bridge, typed
mutation services, Firestore, source-linked reports, approvals, and activity
projection. The repository also includes release tooling, a Next.js product UI,
Firebase Auth emulator browser journeys, deployment scripts, observability
controls, and recovery utilities.

This is still a **release candidate under construction**, not a deployable
public beta. Every coordinator event route now executes deterministic persisted
behavior before its claim is completed, including terminal approved-material
continuation. All currently identified non-cloud implementation blockers are
resolved; remaining gates require deployed auth/operations evidence, a
configured model, or human release review. The canonical evidence checklist is
[tasks/todo-v1.md](../tasks/todo-v1.md).

## Locally verified on 2026-08-08

- uv locked sync: passed
- Ruff check and format: passed
- Mypy app: passed
- Backend pytest: 252 passed, 18 emulator-dependent skipped
- Full Firestore emulator integration: 92 passed
- Firestore repository contract: 8 passed
- Routed workflow Firestore restart: passed
- Production readiness: 13 passed, no xfails
- Fixture eval: 8/8 cases and mutation diffs passed
- Deliberate regression eval: forbidden mutation detected as expected
- Capacity baseline: 5/5 scenarios passed
- Dry demo rehearsal: 3/3 runs passed
- Frontend install, checks, and build: passed with 9 unit tests
- Playwright desktop/mobile: 15 passed, 11 intentional device skips
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

## Confirmed implementation

- Production code has no _PROJECT_DB or datetime.utcnow() dependency.
- Firestore transactions preserve project partitions, optimistic versions, and
  cached read versions for cross-collection mutation sets.
- Task, issue, material, request, report, attachment, approval, run, and activity
  state are durably projected by the canonical Daily Site Update path.
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
