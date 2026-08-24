# Judge Testing Instructions

The official testing surface is the authenticated hosted application. The
deterministic `/demo` route is orientation only and does not execute the live
agent workflow.

## Access

**Hosted application:** https://ogaforeman-cloud-2026.web.app/

**API readiness:** https://oga-api-staging-dc62gfsg7a-ew.a.run.app/health/ready

No private credentials are required. Select **Create account** and use a
judge-controlled email address and password. Create only synthetic project and
site data.

## Golden Scenario

1. Create a project with First-floor blockwork, Electrical rough-in, and
   First-floor plastering. Add the dependency order, Cement Bags, and a
   100-bag plastering requirement.
2. Confirm the project overview shows the planned tasks and material ledger.
3. Open **Site update** and submit:

   ```text
   First-floor blockwork is complete. The electrician did not come today. We
   have 10 bags of cement left. Plastering starts tomorrow.
   ```

4. Open the run view and observe processing, then `waiting_for_approval`.
5. Confirm blockwork completed; electrical remains blocked; plastering risk,
   the 90-bag shortage, material request, Daily Log, and Activity history are
   present.
6. Resolve the exact pending approval. Confirm the original run continues and
   the approved action occurs once.
7. Submit an authenticated delivery-delay event for the canonical material
   request. Do not send OG a conversational prompt. Confirm the autonomous risk,
   follow-up, delayed request, and Google Chat notification.
8. Refresh the browser and sign out/in. Confirm the same Firestore-backed state
   remains visible.

Use a new synthetic project for a clean repeat. Never upload real customer,
worker, supplier, or site data.

## Multimodal path

1. Submit a synthetic site photo or short English voice note through **Site
   update**.
2. Keep uploads within the displayed size and attachment limits.
3. Confirm upload verification completes before the event is accepted.
4. Confirm the resulting activity identifies the attachment and run without
   exposing private object URLs, prompts, or hidden reasoning.

## Expected safety behavior

- Negated or ambiguous language does not complete a task.
- Purchases, supplier commitments, financial actions, task cancellation, major
  schedule changes, and safety-critical actions require human approval.
- Duplicate submissions and delivery events do not duplicate mutations.
- Users without project membership cannot read or mutate the project.
- Activity metadata contains outcomes and identifiers, not secrets or
  chain-of-thought.

## Local reproduction

Use the [README setup instructions](../../README.md). They describe deterministic
local orientation, emulator-backed testing, live Gemini rehearsal, and cloud
deployment. Pinned installs are `uv sync --all-extras --locked` and `npm ci`.

## Public evidence

The submission demonstrates the deployed revision, matching Git provenance,
ADK workflow/session identifiers, Firestore state, Activity history, and
correlated Cloud Logging/Trace evidence. The public video is no longer than
four minutes, is hosted on YouTube or Vimeo, and is playable while signed out.

The architecture and production agent inventory are available in
[`ARCHITECTURE.md`](ARCHITECTURE.md) and
[`AGENT_INVENTORY.md`](AGENT_INVENTORY.md). The recording shot list is maintained
separately from the public submission materials.
