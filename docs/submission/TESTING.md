# Judge Testing Instructions

Status date: **August 23, 2026**

The official testing surface is the authenticated hosted application. The
deterministic `/demo` route is useful for orientation but does not execute the
live agent workflow and must not be used to evaluate backend action.

## Access

**Hosted application:** https://ogaforeman-cloud-2026.web.app/

**API readiness endpoint:**
https://oga-api-staging-dc62gfsg7a-ew.a.run.app/health/ready

**Judge email:** `SUBMISSION BLOCKER: create a dedicated synthetic-data judge account`

**Judge password:** `SUBMISSION BLOCKER: place the credential only in Devpost's private testing instructions, never in Git`

**Synthetic project:** `SUBMISSION BLOCKER: provide the seeded project name and ID`

The account must be free, enabled, and available through the end of judging on
October 1, 2026. It must have only the project role needed for the scripted test.
Do not reuse an owner or personal account.

## Five-minute judge path

1. Open the hosted application and sign in with the private Devpost credential.
2. Select the named synthetic project. Confirm the dashboard shows tasks,
   blockers, materials, approvals, reports, and recent activity.
3. Open **Site update**, submit this text, and retain the returned run ID:

   ```text
   First-floor blockwork is complete. The electrician did not come today. We
   have 10 bags of cement left. Plastering starts tomorrow.
   ```

4. Open the run view and wait for a terminal or `waiting_for_approval` state.
   The UI should show intermediate workflow progress without duplicating prior
   actions on refresh.
5. Verify that First-floor blockwork completed; the electrician's absence
   created an Electrical rough-in blocker and follow-up; Cement Bags shows 10
   against the 100-bag plastering requirement; the request is exactly 90 bags;
   and the report/activity view changed.
6. Open the pending cement approval. Confirm no supplier-facing commitment was
   created before approval. Resolve the exact approval version, observe the
   original run continue, then submit an authenticated operator delay and verify
   the delivery-risk state plus real Google Chat outcome.
7. Refresh the browser. The run, approval, mutations, and activity history
   should remain visible because they are backed by Firestore.

The seeded data must be reset between judge runs or use per-run unique event
IDs so previous state does not obscure results. Submission owners should not
delete production collections to reset a demo; use the reviewed synthetic-data
seed/reset path for the dedicated judge project.

## Multimodal path

To test the user-facing capture flow:

1. Submit a synthetic site photo or short English voice note through the same
   **Site update** surface.
2. Keep each file within the configured limits: no more than ten attachments,
   50 MiB per upload, and 18 MB of model media input.
3. Confirm upload verification completes before the event is accepted.
4. Confirm the resulting activity identifies the attachment and run without
   exposing the private object URL, transcript internals, prompt, or hidden
   reasoning.

Only synthetic, entrant-owned media should be used. Do not upload real worker,
customer, or site information into the judge project.

## Expected safety behavior

- Negated or ambiguous language does not complete a task.
- A material request may be prepared automatically, but a purchase, supplier
  commitment, financial action, task cancellation, major schedule change, or
  safety-critical action cannot be auto-approved.
- A duplicate submission or delivery does not duplicate domain mutations.
- A user without project membership cannot read or mutate the project.
- Activity metadata shows outcomes and identifiers, not chain-of-thought,
  secrets, raw prompts, or unrestricted media URLs.

## Local reproduction

Use the exact [README setup instructions](../../README.md). They provide three
separate paths:

- deterministic local orientation with no Google Cloud credentials;
- emulator-backed integration and live-Gemini rehearsal;
- reviewed Google Cloud staging deployment.

Pinned dependency installs are `uv sync --all-extras --locked` and `npm ci`.
The repository does not require a judge to infer environment variables or use a
production database for local testing.

## Owner verification commands

These commands are for the submission owner to run before declaring the build
ready. Record the commit SHA, timestamps, deployed revision names, and JSON
artifacts. Do not paste credentials into captured output.

```bash
uv sync --all-extras --locked
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/production_readiness
.venv/bin/python scripts/run_evals.py --adapter fixture
.venv/bin/python scripts/run_golden_evals.py --adapter fixture
.venv/bin/python scripts/check_docs.py

cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

After deployment, run the documented authenticated workflow, observability,
backup, scheduler, rollback, and live-Gemini checks from `scripts/` and
`infra/`. A dry run or local emulator pass is not cloud evidence.

The deploy itself must finish the source-provenance gate. Verify:

```bash
curl "$OGA_STAGING_API_URL/api/v1/version"
cat artifacts/operations/staging-deployment-current.json
```

The endpoint must return `git_sha`, `build_timestamp`, `app_version`, and
`environment`; its Git SHA must equal the submitted repository commit. Its
service and revision must equal Cloud Run's latest ready API revision. The
generated artifact must report `passed: true`, `repo_git_sha`,
`build_timestamp`, `deployment_timestamp`, `source_tree_dirty: false`, the safe
`version_response`, and resolved `sha256` digests plus deployment timestamps for
the API, worker, and web revisions. The verifier derives `repo_git_sha` from
repository `HEAD` rather than accepting a manually typed SHA. The current
artifact is ignored and must be attached to the submission record rather than
committed after the deploy.

The approval-resume release gate is:

```bash
.venv/bin/python scripts/run_adk_resume_gate.py
```

The wrapper requires both `FIRESTORE_EMULATOR_HOST` and
`STORAGE_EMULATOR_HOST`, runs only the approved restart case, and exits nonzero
if either endpoint is absent. A skipped test is not release evidence.

Then repeat the same Golden flow against staging: stop after
`waiting_for_approval`, record the ADK app/session/invocation/workflow IDs,
force a new worker revision or process using the same immutable image, approve,
and verify the same IDs, one approved-request continuation, one resumed/completed
activity pair, a terminal original run, and a completed site update. Local SQLite,
in-memory stores, or reconstruction of the generic event workflow do not satisfy
this production gate.

## Taskmaster ADK ownership proof

The following focused suite proves the explicit workflow graphs and their
critical outcomes. It is intentionally separate from project-import evals:

```bash
.venv/bin/pytest -q \
  tests/workflows/test_adk_runtime.py \
  tests/workflows/test_site_update_adk_resume.py \
  tests/integration/test_e2e_runtime.py::test_e2e_api_uses_production_worker_and_resumes_the_same_run \
  tests/integration/test_delivery_delay_intake.py \
  tests/integration/test_delivery_notifications.py \
  tests/contract/test_notification_provider.py \
  tests/integration/test_worker_routed_workflows.py::test_delivery_delay_updates_request_and_creates_downstream_risk \
  tests/integration/test_conversation_api.py::test_project_answer_is_generated_from_authorized_live_context \
  tests/unit/test_google_chat_notification.py \
  tests/unit/test_gemini.py::test_gemini_conversation_agent_generates_only_authorized_grounded_citations \
  tests/unit/test_adk_telemetry.py
```

The provider-only live integration check is an explicit external side effect
and refuses a dirty worktree. Run it from the final configured commit, confirm the resulting message in the
dedicated Google Chat space, and preserve its ignored artifact:

```bash
export NOTIFICATION_PROVIDER=google_chat
.venv/bin/python scripts/run_google_chat_live_check.py \
  --confirm-send send-google-chat-live-check \
  --output artifacts/operations/google-chat-live-current.json
```

This check never prints or persists the webhook URL. The full staging
delivery-delay workflow must separately show the completed Firestore outbox
record and the same provider message ID before its `AgentRun` reports success.

Inspect the ADK session event history or filtered structured logs for:

- site update: `retrieve_authorized_context`, `interpret_evidence`,
  `resolve_canonical_entities`, `progress_node`, `blocker_node`,
  `material_node`, `merge_actions`, `evaluate_policy`, and
  `execute_site_update`;
- delivery delay: `retrieve_authorized_request_context`,
  `assess_material_schedule_impact`,
  `mark_material_request_delayed_tool`, `create_delivery_risk_tool`,
  `create_delivery_follow_up_tool`, and `deliver_delivery_notification_tool`;
- conversation: `classify_intent`, `retrieve_authorized_context`,
  `resolve_canonical_entities`, then either
  `reason_over_authorized_context` or `invoke_conversation_typed_tools`.

The current working tree has passed focused Ruff and Python compilation only.
The runtime commands above remain an owner-run gate and must not be recorded as
passing until their artifacts are captured from the final clean commit.

The delivery-delay integration case must show a non-empty direct task set and
its downstream dependency expansion. It replays the same authenticated operator
event and asserts exactly one follow-up and one externally delivered notification. The workflow graph test also
asserts that the legacy routed-event executor rejects `DELIVERY_DELAYED`.

## Current evidence and open gates

The repository contains unit, contract, workflow, integration, browser,
security, production-readiness, and deterministic evaluation suites. It also
contains checked-in operational artifacts. Those artifacts are historical and
must not be assumed to represent the current commit.

As of the status date:

- the hosted web URL and API readiness endpoint respond;
- the in-process production-worker E2E approval path passed on 2026-08-23
  (`1 passed`, 24.33 seconds), preserving the same logical run and using the
  production worker continuation route;
- the backed restart command produced two skips because Firestore and Storage
  emulator endpoints were absent. This is recorded as **not run**, not passed;
- the stale tracked staging deployment artifact was removed. A new deploy must
  produce a passing ignored `staging-deployment-current.json` artifact for the
  final clean commit;
- the latest checked-in live core Gemini evaluation is below its release
  threshold and must be rerun after correction;
- the replacement eight-check Golden operational evaluator must pass 8/8 with
  100% canonical entity resolution through the billed Vertex route; passing
  project-import cases are separate evidence and cannot compensate;
- the live artifact must identify the Vertex project/location, match the
  submitted commit, and report `source_tree_dirty: false`;
- current deployed voice/photo processing, approval continuation, private media
  access, alert delivery, and end-to-end log correlation still require fresh
  evidence;
- Google ADK `ResumabilityConfig` is experimental. The tested dependency is
  pinned at `google-adk==2.6.2`; upgrades must rerun the backed and staging
  restart gates;
- the authenticated staging smoke must verify the exact
  `waiting_for_approval` state and then exercise approval continuation.

These are submission blockers, not judge troubleshooting notes. Submit only
after [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) records current passing
evidence.

## Support during judging

**Contact:** `SUBMISSION BLOCKER: add a monitored support email in Devpost`

If a judge cannot sign in or the seeded scenario was already consumed, the
submission owner should restore only the synthetic judge project and preserve
the incident and recovery evidence. Keep the application and repository
available free of charge and without restriction until judging ends.
