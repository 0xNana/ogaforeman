# Four-Minute Demo Script

Target duration: **3:45**. Hard stop: **3:55**. Devpost evaluates only the first
four minutes. Record in English or add accurate English subtitles.

The proof-of-action segment must be a continuous, unedited live execution. The
public `/demo` page is a deterministic product tour and is not competition
proof. Use the authenticated deployed application with real Gemini and the
current Google Cloud revision.

## Before recording

- Deploy a clean, current commit and write down the commit SHA, image digest,
  Cloud Run revision names, and public URL.
- Open `/api/v1/version` and the generated deployment-provenance artifact.
  Confirm both show the submitted full SHA, current API revision, clean source
  state, and resolved image digests before recording.
- Seed the locked Golden project: First-floor blockwork in progress, Electrical
  rough-in and First-floor plastering planned with dependencies, Cement Bags
  with a 100-bag requirement, a canonical approver, and a reset authenticated
  operator delivery-delay fixture.
- Prepare a short original voice note containing the exact Golden update below.
  Confirm the transcript before submission; use text input if transcription
  changes any entity, quantity, negation, or timing. Remove personal information
  and third-party marks.
- Sign in with an approved demo user and verify the user has the role needed to
  submit updates and resolve the approval.
- Open browser tabs for the product, Cloud Run revision, Firestore, and a
  filtered Cloud Logging query. Increase browser zoom enough for video text to
  be legible.
- Turn off notifications and hide project numbers, emails, tokens, secrets,
  billing data, unrelated logs, and private media.
- Run the complete rehearsal once. Record only when every item in
  [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) is satisfied.
- Confirm the deployed worker configuration visibly reports
  `NOTIFICATION_PROVIDER=disabled` for the temporary staging scope and that its
  outbox outcome is `skipped`; the local/test logging provider is not acceptable
  competition evidence.
- Run the billed Vertex Golden operational evaluator from the exact deployed
  commit. Do not record unless it passes 8/8 with 100% canonical resolution.
- Run the backed-service approval restart test, then repeat it against staging
  with a real worker revision/process restart between `waiting_for_approval`
  and the approval decision. Do not use the same-run resume narration unless
  both gates pass and the approved request continuation completes exactly once.

## Shot list and narration

### 0:00-0:20 - The friction

**Screen:** Project dashboard with a real synthetic schedule, material stock,
and current activity.

**Narration:**

> On a construction site, a thirty-second field update can imply an hour of
> coordination: update progress, find the affected task, record a delay,
> calculate a material shortage, assign follow-up, ask for the right approval,
> and refresh the daily report. OG Foreman completes that workflow instead of
> returning another chat answer.

### 0:20-0:42 - Architecture and Google Cloud proof

**Screen:** Show `architecture-diagram.svg` for eight seconds, then the Google
Cloud Console Cloud Run service details for the deployed API and worker. Make
the current revision and image tag visible. Briefly show the `.run.app` API URL.

**Narration:**

> The authenticated Next.js app submits a durable project event. Pub/Sub invokes
> a private Cloud Run worker. Google ADK coordinates the workflow, Gemini 3.6
> Flash interprets bounded evidence, typed tools mutate, and Firestore remains
> the source of truth. These are the live API and worker revisions for the
> commit I am demonstrating.

### 0:42-1:13 - Submit messy multimodal evidence

**Screen:** Return to the product. Start a site update, attach the prepared
photo, record or attach the short voice note, and submit. Keep the upload and
run-state transition visible.

Suggested voice note:

> First-floor blockwork is complete. The electrician did not come today. We
> have 10 bags of cement left. Plastering starts tomorrow.

**Narration:**

> This is the same locked update used by our billed Vertex release gate. It
> combines completion, an absent trade, absolute stock, and next focus in one
> field report.

### 1:13-2:08 - Prove autonomous action

**Screen:** Keep one continuous product recording. Show the run progress and
then the changed project views. Highlight exact, visible results:

- First-floor blockwork resolved to the canonical task and became complete;
- the electrician's absence resolved to Electrical rough-in and created a
  blocker plus follow-up;
- Cement Bags became 10 on hand against the persisted 100-bag requirement;
- the material request contains the exact 90-bag shortage;
- the report and activity feed refreshed;
- stable event and run identifiers are visible where the UI exposes them.

**Narration:**

> One input is now driving several coordinated actions. Gemini extracted the
> evidence-backed facts, while deterministic services resolved canonical
> project entities. Each typed tool rechecked identity, evidence, confidence,
> policy, version, and idempotency. Every durable change added an activity event
> in the same transaction. The absence was not mistaken for completion, and
> deterministic arithmetic produced the exact ninety-bag shortage.

Do not narrate a result until it is visible. If the run fails or the result is
wrong, stop and fix the product; do not hide the failure with editing.

### 2:08-2:42 - Human authority boundary

**Screen:** Open the pending 90-bag cement request approval. Show that the run
is waiting and no supplier commitment exists. Approve it with the demo
approver and show the original run complete. Then use the authenticated operator
delivery-delay action to report the revised date and supplier-stated reason.
Keep the resulting project risk and skipped external-delivery activity visible together.

**Narration:**

> Safe follow-through was automatic, but a supplier-facing commitment crosses
> the approval boundary. The workflow paused durably. I am approving the exact
> version now; the same run resumes without repeating its earlier mutations.
> A real operator report now enters through the authenticated external boundary.
> Nobody prompted OG: the project changed, ADK loaded the request, material, and
> affected tasks, expanded the dependency impact, and continued with an audited
> risk, follow-up, and one honestly recorded skipped external-delivery outcome.
> V1 never sends money or places a binding order.

### 2:42-3:12 - Prove durable state and observability

**Screen:** Show Firestore documents for the same synthetic project: the run,
approval, task or blocker, material request, and activity event. Then show Cloud
Logging filtered by the same `run_id` or `event_id`, including worker service,
workflow, agent/tool labels, and successful completion. If available, show the
correlated Cloud Trace entry.

**Narration:**

> This is the same run in Firestore, including its approval and atomic activity
> history. Here is the correlated Cloud Run worker execution in Cloud Logging.
> Domain truth survives process loss; model context and browser state are not
> used as the database. The stage labels show ADK itself owned context,
> interpretation, all three parallel analyses, policy, typed tools, approval,
> and continuation. The delivery-delay workflow separately created this risk,
> follow-up task, and external message. The outbox record includes the provider
> message ID and completed delivery state; no webhook credential is displayed.

### 3:12-3:32 - Prove agentic project conversation

**Screen:** Ask, "What is blocking plastering, and what should we review?"
Show the live, cited answer, then briefly show its correlated ADK nodes in the
same log view.

**Narration:**

> Project conversation uses the same authority split. ADK classified this
> request, retrieved only my authorized live project context, resolved the
> referenced records, and Gemini generated this cited answer. A requested
> change would enter the typed-tool and confirmation or approval branch instead.

### 3:32-3:50 - Close on Taskmaster value

**Screen:** Return to the updated dashboard, with progress, shortage, follow-up,
report, and completed run visible together.

**Narration:**

> OG Foreman turns messy field evidence into verified operational follow-through:
> autonomous where it is safe, explicit human control where authority matters,
> and durable evidence for every action. That is a complete background workflow,
> not just a chatbot.

## Recording failure conditions

Do not publish a take if any of these occur:

- the first four minutes omit the problem, value, application in action, or
  visible Google Cloud proof;
- the workflow uses `USE_FAKE_MODEL=true`, `DEMO_MODE=true`, local emulators, or
  the deterministic `/demo` route;
- the deployed image is not traceable to the submitted repository commit;
- the recording cuts across the proof-of-action workflow;
- a claimed mutation, approval pause, continuation, or log correlation is not
  visible;
- secrets, personal data, hidden prompts, chain-of-thought, or private site
  media are exposed;
- the upload is unlisted, private, longer than four minutes, or lacks English
  narration/subtitles.
