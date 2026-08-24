# Final Submission Video Production Plan

Owner: `SUBMISSION BLOCKER: assign a named owner`
Target lock date: `SUBMISSION BLOCKER: set a date before August 31, 2026`
Public URL: `SUBMISSION BLOCKER: add public YouTube or Vimeo URL`

This is the internal production record for the OG Foreman hackathon video. The
full narration and shot list are in [`Demo script`](DEMO_SCRIPT.md).

## Non-negotiable rules

- Publicly visible on YouTube or Vimeo. **Unlisted is not public.**
- No longer than four minutes; target 3:45 and hard-stop editing at 3:55.
- English narration or accurate English subtitles.
- Explain the problem and value, then demonstrate the application in action.
- Visibly prove the backend is running on Google Cloud by showing the Cloud Run
  dashboard/revision, a `.run.app` URL, and correlated Cloud Logging or Vertex
  AI evidence.
- Include a continuous, unedited live execution of the agent performing the
  multi-step workflow through UI, database, and/or log changes.
- Show the actual submitted deployment with real Gemini. The deterministic
  `/demo`, fake model, emulator, screenshots, and stale evidence do not qualify.
- Show staging configured with `NOTIFICATION_PROVIDER=google_chat`; a logging
  provider result is development evidence only.
- Do not show secrets, tokens, passwords, raw private media, personal data,
  billing details, prompts, or chain-of-thought.

## Required proof packet

Capture these values before recording and keep them in the private release
record:

| Evidence | Value |
| --- | --- |
| Final commit SHA | `PENDING` |
| Google Cloud project and region | `PENDING` |
| Web revision and image digest | `PENDING` |
| API revision and image digest | `PENDING` |
| Worker revision and image digest | `PENDING` |
| Gemini model and prompt version | `PENDING` |
| ADK durable session backend | `PENDING` |
| Synthetic project ID | `PENDING` |
| Event ID | `PENDING` |
| Run ID | `PENDING` |
| Approval ID | `PENDING` |
| Trace ID or saved log query | `PENDING` |
| Public YouTube/Vimeo URL | `PENDING` |

All runtime evidence must resolve to the same deployed commit. If the Cloud Run
revision is older than the final Git SHA, redeploy and repeat the rehearsal.
Keep `/api/v1/version` and
`artifacts/operations/staging-deployment-current.json` ready for the recording;
the full SHA, API revision, clean-tree flag, and three resolved image digests
must agree. The stale tracked `0aa4a2c` artifact was removed; only fresh evidence
generated from the final clean staging deployment is acceptable.
Do not record the approval sequence until a separate staging rehearsal has
paused the Golden run, restarted the worker process/revision, approved it, and
proven unchanged ADK app/session/invocation/workflow IDs plus one
approved-request continuation and one terminal original run.

## Demo fixture

Use a disposable synthetic project owned by the entrant. It needs:

- one authenticated foreman and one canonical approver;
- First-floor blockwork in progress, Electrical rough-in planned, and
  First-floor plastering planned for the next day;
- a dependency path from blockwork through electrical work to plastering;
- Cement Bags with a persisted 100-bag upcoming requirement; the submitted
  update reports 10 bags left, yielding a visible 90-bag shortage;
- an approved material request plus an authenticated operator delay fixture;
- empty or clearly reset run, approval, and activity state;
- a short original voice recording of the locked Golden update. Confirm its
  transcript exactly before submission; use text input if transcription drifts.

Use the reviewed seed/reset process. Never clear a shared production database or
reuse a real construction project for the recording.

## Screen layout

Prepare four browser tabs in this order:

1. Hosted OG Foreman project.
2. Architecture diagram.
3. Google Cloud Console Cloud Run service/revision.
4. Firestore and Cloud Logging filtered to the synthetic project/run.

Use a 16:9 canvas at 1920x1080 or 2560x1440. Set browser zoom so IDs and status
labels are readable after video compression. Close bookmarks, email, chat,
other Cloud projects, and unrelated tabs. Disable desktop and phone
notifications. Use a clean browser profile with no password manager overlays.

## Four-minute recording script

Use the hosted application and real staging backend. The animated `/demo` route
is never evidence.

### 0:00-0:25 - Problem and premise [READY]

**Screen:** Hosted OG Foreman and the signed-in Ridge House project. **Action:**
Explain that voice, photos, text, and external events become verified project
state and follow-through. Do not claim every Gemini path uses ADK.

### 0:25-0:45 - Planned truth [READY]

**Screen:** Tasks, Dependencies, Materials, and Requirements. **Action:** Show
blockwork, its dependency into plastering, the 100-bag cement requirement, and
current inventory.

### 0:45-1:25 - Real voice and photo update [READY]

**Screen:** Site Update composer. **Action:** Submit the locked Golden Scenario
voice/photo update once: blockwork complete, electrician absent, 10 bags left,
plastering tomorrow. Show the accepted update and processing run.

### 1:25-1:55 - Autonomous follow-through [READY]

**Screen:** Task, issue, material, approval, Daily Log, and Activity views.
**Action:** Without another prompt, show canonical completion, electrical
blocker, downstream plastering risk, 100-minus-10 equals 90-bag shortage,
material request, and Daily Log update. Pause at `WAITING_FOR_APPROVAL`.

### 1:55-2:20 - Approval and native resume [READY]

**Screen:** Approval detail and the same run/session/invocation evidence.
**Action:** Approve as manager. Show native ADK continuation after the restart
rehearsal, unchanged original run identity, approved request, and one
consequential external action.

### 2:20-2:55 - Autonomous delivery-delay reaction [READY]

**Screen:** Authenticated external event boundary, then OG Activity/risk/follow-
up and Google Chat. **Action:** Submit `DELIVERY_DELAYED` externally; do not
prompt OG. Show the dedicated ADK workflow, one risk, one follow-up, and one
real notification. Hide webhook secrets.

### 2:55-3:20 - Activity and conversation [READY]

**Screen:** Activity timeline and conversation panel. **Action:** Ask “What is
blocking plastering?” Show the grounded, cited answer from authorized live
records, not a canned response.

### 3:20-3:45 - Architecture and Google Cloud proof [READY]

**Screen:** Architecture diagram, Cloud Run revision, `/api/v1/version`, and
correlated Cloud Logging/Trace or ADK evidence. **Action:** Explain direct
structured Gemini extraction for initialization, and ADK Runner/workflows,
typed tools, domain services, and Firestore for operations. Point to matching
Git SHA, revision, digest, and trace/run IDs.

### 3:45-4:00 - Closing thesis [READY]

**Screen:** Final Ridge House state. **Action:** “OG Foreman turns messy site
evidence into verified project state, pauses consequential actions for people,
and continues follow-through when the project changes.”

## Recording order

1. Rehearse restart/resume and the external delivery-delay event first.
2. Record 0:45-2:55 as one continuous proof-of-action take.
3. Record architecture and Cloud Run proof only after the live take works.
4. Use minimal labels/subtitles; never cover IDs, timestamps, or logs.
5. Export under four minutes and inspect playback while signed out.

## Verification flags

- Live functionality is marked ready from the supplied release checklist; recheck
  the exact deployed revision on recording day.
- **Video itself: UNVERIFIED until upload:** duration, public visibility,
  logged-out playback, captions, and visible Google Cloud proof.
- **Public URL: TODO** until a YouTube/Vimeo URL is entered above and in Devpost.

## Evidence that must be visible

- Public hosted URL and signed-in synthetic project.
- Current Cloud Run API and worker revision names and image/commit identity.
- Live submission of the locked Golden update and run-state change.
- Multiple autonomous domain changes from the single input.
- First-floor blockwork resolves canonically and reaches completed.
- The electrician's absence becomes an Electrical rough-in blocker and
  follow-up, not a completion.
- Cement Bags resolves canonically to 10 on hand against 100 required.
- Correct shortage arithmetic: 100 required minus 10 available equals 90 bags.
- Pending approval with no premature external commitment.
- Canonical approver decision and continuation of the original run, followed by
  a separately authenticated operator delivery-delay report.
- Delivery delay produces one risk, one source-linked follow-up task, and one
  externally visible Google Chat notification through its dedicated ADK graph.
- Structured logs visibly identify the Daily Site Update context,
  interpretation, resolution, parallel progress/blocker/material, merge,
  policy, tool, and continuation nodes for the same run.
- One live project question returns a Gemini-generated, record-cited answer;
  its log path shows ADK classification, authorized context retrieval,
  canonical resolution, and grounded reasoning rather than a response template.
- Firestore run, approval, mutation, and `ActivityEvent` records.
- Cloud Logging or Cloud Trace correlation for the same event/run.
- Final dashboard/report showing the combined operational outcome.

## Privacy and claims review

- [ ] Every user, project, image, recording, schedule, and material record is
  synthetic or entrant-owned.
- [ ] No Google Cloud secret, API key, bearer token, password, service-account
  credential, billing account, private email, or full project number is visible.
- [ ] No customer, worker, subcontractor, supplier, or real site data appears.
- [ ] No third-party advertising, unlicensed music, logo, or asset appears.
- [ ] No hidden prompt, model scratchpad, chain-of-thought, or unrestricted
  signed media URL appears.
- [ ] Claims match what the current application visibly does.
- [ ] The Google Chat message is visibly real, while its webhook URL, key, and
  token remain hidden; no purchase/payment claim is made.
- [ ] No reliability, restart, backup, alert, or model-quality gate is claimed
  unless its current evidence is visible or linked.

## Upload settings

Suggested title:

```text
OG Foreman - Autonomous Construction Follow-Through | All Things Agentic Hackathon
```

Suggested description:

```text
OG Foreman turns messy construction-site updates into verified project state
and operational follow-through using Gemini 3.6 Flash, Google ADK, Cloud Run,
Firestore, Cloud Storage, and Pub/Sub.

Built for entry into Google's All Things Agentic Hackathon, Taskmaster category.

Project: https://ogaforeman-cloud-2026.web.app/
Source: https://github.com/0xNana/ogaforeman
```

Upload as **Public**, enable accurate English captions, allow normal playback
without sign-in, and avoid age or geographic restrictions. Do not use an
unlisted visibility setting.

## Final acceptance

- [ ] Final duration is 3:30-3:55.
- [ ] Audio is intelligible at normal laptop volume and captions are accurate.
- [ ] Text remains legible at 1080p playback.
- [ ] Proof-of-action segment is continuous and unedited.
- [ ] Cloud Run and correlated Google Cloud execution are unmistakable.
- [ ] The first four minutes contain the entire problem, value, demo, and proof.
- [ ] A signed-out browser can open and play the video at full quality.
- [ ] Public visibility is confirmed from a second account/device.
- [ ] Video URL is added to Devpost, `docs/submission/DEVPOST.md`, and
  `docs/submission/SUBMISSION_CHECKLIST.md`.
- [ ] Devpost preview is checked before the deadline.

Official rules:
https://allthingsagentichackathon.devpost.com/rules
