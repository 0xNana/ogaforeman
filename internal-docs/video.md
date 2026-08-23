# Final Submission Video Production Plan

Owner: `SUBMISSION BLOCKER: assign a named owner`
Target lock date: `SUBMISSION BLOCKER: set a date before August 31, 2026`
Public URL: `SUBMISSION BLOCKER: add public YouTube or Vimeo URL`

This is the internal production record for the OG Foreman hackathon video. The
public narration and timing live in
[`docs/submission/DEMO_SCRIPT.md`](../docs/submission/DEMO_SCRIPT.md).

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

## Recording order

1. Record the complete proof-of-action workflow in one take. Do not cut between
   submit, autonomous mutations, approval pause, approval decision, and resumed
   state.
2. Record the architecture and Cloud Run opening only after the live take works,
   so the revision shown cannot drift.
3. Record the close on the final updated dashboard.
4. Add only minimal title labels and subtitles. Never cover state, IDs, revision
   names, timestamps, or log fields with graphics.
5. Verify the exported duration and inspect the first four minutes from a
   signed-out viewer account.

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
