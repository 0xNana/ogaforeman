# OG Foreman Prize Presentation

Status: **canonical presentation and recording source of truth**

This document replaces `DEMO_SCRIPT.md` and `video.md`. Do not maintain a
second script, shot list, proof checklist, or narration elsewhere.

## The decision

The presentation tells one continuous story:

> A project manager loads the Ridge House plan once. OG turns the reviewed plan
> into durable project truth. Later, one messy field update triggers verified
> progress, blocker, material, approval, reporting, and follow-through work
> without another prompt.

Use only [`projects/ridge-house-plan.md`](projects/ridge-house-plan.md) as the
presentation project source. It contains the exact Golden task names,
dependency chain, initial stock, and 100-bag plastering requirement. The other
files in `internal-docs/projects/` are import-format test samples, not alternate
demo projects.

Reliability wins over file-format theater. A successful Markdown import that
feeds the exact proven operational workflow is stronger than a polished PDF
whose extracted entities do not match the live Golden path.

## What we are trying to win

The primary target is **The Taskmaster**, with a credible path to the Grand
Prize, Best Architectural Design, Best Multimodal UX, or Individual/Hobbyist
prize. A submission can win only one prize, so the video should maximize the
overall score rather than look tailored to a secondary category.

The [official rules](https://allthingsagentichackathon.devpost.com/rules) weight
the score as follows:

| Criterion | Weight | What this video must prove |
| --- | ---: | --- |
| Innovation and operational utility | 40% | One field report causes high-value background work, not another chat response. |
| Architectural discipline and tech stack | 30% | Gemini reasons, ADK coordinates, typed tools mutate, Firestore persists, and approvals bound authority. |
| Demo and production readiness | 30% | A clear under-four-minute story, uninterrupted live action, current Google Cloud proof, and reproducible documentation. |

Our strongest angle is not “AI for construction.” It is:

> **From an ordinary project document to safe autonomous follow-through.**

That is the twist. PMs do not rebuild their schedule inside a demo app. They
bring the project plan they already have; OG grounds every later action in the
reviewed, durable project created from that source.

## Truthful architecture story

Project initialization and operational autonomy have different authority
boundaries. Keep this distinction crisp:

```text
Ridge House document
-> direct Gemini structured extraction
-> deterministic validation
-> human review and confirmation
-> one typed Firestore commit
-> durable project truth

voice + photo + text field update
-> authenticated event
-> Pub/Sub
-> private Cloud Run worker
-> Google ADK workflow
-> bounded Gemini interpretation
-> deterministic canonical resolution and policy
-> typed tools
-> Firestore mutations + atomic ActivityEvents
-> approval pause and continuation
```

Never say that ADK performs project import. Never say Gemini writes Firestore,
approves a purchase, or invents canonical IDs. Never describe the disabled
staging notification as sent.

## Locked presentation data

### Project source

- File: `internal-docs/projects/ridge-house-plan.md`
- Project: Ridge House Residential Build
- Canonical operational tasks:
  - First-floor blockwork — in progress, 80%;
  - Electrical rough-in — planned after blockwork;
  - First-floor plastering — planned after electrical rough-in.
- Material: Cement Bags
- Initial on-hand quantity: 25 bags
- Requirement: 100 bags for First-floor plastering
- Approval rule: a manager approves any supplier commitment or purchase

### Locked field update

Use this wording exactly. If voice transcription changes an entity, quantity,
negation, or timing term, use the text path for the final take.

> First-floor blockwork is complete. The electrician did not come today. We
> have 10 bags of cement left. Plastering starts tomorrow.

### Expected result

One accepted update must visibly produce all of the following exactly once:

1. First-floor blockwork resolves canonically and completes.
2. “Did not come” does not complete Electrical rough-in; it creates a blocker
   and follow-up.
3. First-floor plastering is identified as downstream work at risk.
4. Cement Bags becomes 10 on hand.
5. The persisted 100-bag requirement produces an exact 90-bag shortage.
6. A material request and approval are created without a purchase or supplier
   commitment.
7. The Daily Log and Activity timeline update.
8. The same run pauses for the exact approval and continues once after the
   authorized decision.
9. A later authenticated delivery delay updates the request, risk, and
   follow-up without a chat prompt.
10. Staging records external delivery as `skipped`, provider `disabled`, zero
    attempts, and no provider message ID.

## Four-minute production script

Target: **3:42**. Hard stop: **3:55**. Everything a judge must understand should
land by 3:42, leaving a safety margin for transitions.

### 0:00–0:16 — Hook: the project plan is not the work

**Screen:** The Ridge House project file beside the hosted New Project screen.

**Action:** Drag or select `ridge-house-plan.md`.

**Narration:**

> A project plan is only the starting point. The real work begins when site
> reality changes and somebody must update the schedule, materials, risks,
> approvals, and team follow-up. OG Foreman turns that coordination burden into
> one durable workflow.

### 0:16–0:43 — Bring the project, do not rebuild it

**Screen:** Upload state, extracted review, and the compact task/material diff.
Keep First-floor blockwork, Electrical rough-in, First-floor plastering, Cement
Bags, 25 on hand, and the 100-bag requirement visible.

**Action:** Review and confirm the import. If live extraction regularly exceeds
this timebox, begin with an already extracted `needs_review` draft and show the
persisted source filename before confirmation. Do not fake or silently cut a
loading result.

**Narration:**

> The PM brings the plan they already maintain. Gemini extracts a typed draft,
> deterministic validation checks identities, dates, dependencies, units, and
> conflicts, and a person reviews it before anything becomes project truth.
> The model never receives write authority.

### 0:43–0:55 — Establish durable truth

**Screen:** Confirmed Ridge House overview with the imported dependency chain
and cement requirement.

**Narration:**

> One confirmation commits the reviewed schedule, dependencies, materials,
> inventory, provenance, and audit events to Firestore. Now OG has the context
> needed to act when the site changes.

### 0:55–2:08 — Proof of action: one uninterrupted field update

This is the mandatory continuous, unedited live execution. Keep the product on
screen from submission through the visible results.

**Screen:** Universal OG composer, synthetic site photo, voice recording or
locked text, run state, then Tasks, Materials, request/approval, Daily Log, and
Activity.

**Action:** Submit the locked field update once. Show these visible results in
this order: blockwork complete, electrical blocker, plastering risk, Cement
Bags at 10, 90-bag shortage/request, Daily Log, waiting approval.

**Narration:**

> Now one messy field report drives the actual coordination work. Gemini
> extracts bounded facts from the authorized text, voice, and photo. Google ADK
> owns the workflow: context, interpretation, canonical resolution, parallel
> progress, blocker and material analysis, policy, typed tools, reporting, and
> approval. Deterministic services calculate one hundred required minus ten on
> hand: exactly ninety bags short. Every mutation writes its audit event in the
> same transaction, and the electrician's absence is never mistaken for task
> completion.

Do not narrate a result before it is visible. If any canonical entity or
quantity is wrong, stop the take; editing around a wrong result destroys the
Proof of Action.

### 2:08–2:38 — Human authority, same workflow

**Screen:** Pending 90-bag request, approval details, original run identity,
decision, and terminal continuation.

**Action:** Show there is no supplier commitment, approve as the canonical
manager, and show the original logical run continue once.

**Narration:**

> Safe project updates happen automatically. A supplier-facing commitment does
> not. OG persists the exact approval and pauses. This authorized decision
> continues the same logical ADK execution without replaying the earlier work.

Only claim survival across process replacement if the final staging rehearsal
has proven it for the submitted revision.

### 2:38–3:03 — The project changes again; OG follows through

**Screen:** Authenticated delivery-delay intake followed by delayed request,
downstream risk, source-linked follow-up, Activity, and skipped outbox outcome.

**Action:** Submit one supplier-stated revised date and reason. Do not prompt OG
in chat.

**Narration:**

> Later, an authenticated operator reports that delivery slipped. Nobody asks
> OG what to do. A separate ADK workflow retrieves the approved request and its
> dependencies, marks the delay, updates risk, creates follow-up, and records
> the external outcome once. Chat delivery is temporarily disabled in staging,
> so the audit truthfully says skipped with zero attempts—not sent.

### 3:03–3:30 — Prove the production architecture

**Screen:** Architecture diagram, current Cloud Run API and worker revisions,
`/api/v1/version`, and a saved Cloud Logging query filtered to the same run or
event. Make matching commit/revision identity and allowlisted ADK node/tool
labels readable. Do not show project numbers, tokens, prompts, or raw media.

**Narration:**

> This is the submitted revision on Google Cloud: an authenticated Next.js app,
> FastAPI on Cloud Run, Pub/Sub into a private worker, Google ADK and Gemini 3.6
> Flash, typed tools, and Firestore as durable truth. Matching run and event IDs
> connect the product state to the workflow and logs.

### 3:30–3:42 — Close on the prize thesis

**Screen:** Final Ridge House dashboard showing the imported project, completed
work, blocker, shortage, approval outcome, risk, follow-up, and activity.

**Narration:**

> OG Foreman turns the project file a PM already has and the field update a
> foreman already gives into verified operational follow-through—autonomous
> where it is safe, human-controlled where authority matters, and auditable all
> the way down.

End immediately. Do not add a feature montage or generic “thank you” slide.

## What stays out of the four minutes

- General project chat: useful, but it makes the Taskmaster story look like a
  chatbot and costs proof time.
- Every supported import format: state this in Devpost; show only Ridge House.
- Test dashboards, local emulators, `/demo`, fixture evaluators, and terminal
  test output.
- Monitoring policies, backup drills, capacity numbers, and exhaustive IAM.
- A tour of all four workflow roots. The video proves one complete vertical
  slice; the architecture and repository document the rest.
- Unsupported claims about money sent, orders placed, safety certification,
  schedule optimization, or external messages delivered in disabled staging.

## Recording gates

Do not record until every blocking gate below is green for the exact deployed
commit.

### Gate 1 — Canonical import

- [ ] A fresh user can upload `ridge-house-plan.md` through `/projects/new`.
- [ ] The review contains the three exact Golden tasks and correct dependency
  order with no unresolved conflict.
- [ ] Cement Bags imports with 25 on hand and a linked 100-bag First-floor
  plastering requirement.
- [ ] Confirmation survives refresh and the project overview shows the same
  Firestore-backed data.
- [ ] Import plus confirmation fits the 39-second presentation timebox, or a
  truthful persisted `needs_review` starting point is prepared.

### Gate 2 — Operational Golden path

- [ ] The billed Vertex Golden evaluator passes 8/8 with 100% canonical
  resolution from a clean submitted commit.
- [ ] The exact field update produces every locked expected result once.
- [ ] The photo and voice assets are synthetic, entrant-owned, short, and free
  of third-party marks or personal data.
- [ ] Voice transcription matches the locked sentence exactly; otherwise the
  final take uses text.

### Gate 3 — Approval and follow-through

- [ ] The run visibly waits before the consequential action.
- [ ] The authorized manager decision continues the original logical run once.
- [ ] Backing-service and final staging process-replacement rehearsals support
  every durability claim used in narration.
- [ ] The later delivery-delay event produces one risk, one follow-up, and one
  `disabled`/`skipped` outcome with zero attempts.

### Gate 4 — Deployment proof

- [ ] Repository HEAD, `origin/main`, `/api/v1/version`, three Cloud Run
  revisions, image labels, and resolved digests identify the same clean commit.
- [ ] The saved log view is filtered to the presentation project/event/run and
  shows readable workflow, agent, node, tool, status, and duration labels.
- [ ] `NOTIFICATION_PROVIDER=disabled` is visible only through safe
  configuration evidence; no Secret Manager value appears.

### Gate 5 — Video and submission

- [ ] Runtime is at most 3:55 and the full scoring story lands by 3:42.
- [ ] The 0:55–2:08 Proof of Action is one continuous, unedited product take.
- [ ] English narration or accurate English captions are present.
- [ ] Text remains legible after export at normal playback size.
- [ ] The public YouTube or Vimeo link plays while signed out and is not
  private or unlisted.
- [ ] Devpost description, testing instructions, architecture diagram, public
  repository, and video all describe the same submitted behavior.

## Recording setup

Use a 16:9 1920×1080 or 2560×1440 canvas. Prepare one clean browser profile and
five tabs in this order:

1. hosted New Project/import screen;
2. hosted Ridge House project;
3. architecture diagram;
4. Cloud Run service/revision and `/api/v1/version`;
5. Firestore/Cloud Logging saved query for the synthetic project.

Increase browser zoom until task names, quantities, status, IDs, and timestamps
remain readable after compression. Hide bookmarks, email, project numbers,
billing, unrelated logs, password managers, and desktop/phone notifications.

Keep this private evidence packet beside the recording checklist:

| Evidence | Final value |
| --- | --- |
| Git commit SHA | `PENDING` |
| Hosted web URL | `PENDING` |
| API and worker revisions | `PENDING` |
| Image digests | `PENDING` |
| Gemini model and prompt version | `PENDING` |
| Synthetic project/source/import IDs | `PENDING` |
| Site update event and run IDs | `PENDING` |
| Approval ID | `PENDING` |
| Delivery-delay event/run/outbox IDs | `PENDING` |
| Saved log/trace query | `PENDING` |
| Public video URL | `PENDING` |

## Execution plan

### P-01 — Validate the presentation source

Acceptance: a fresh deployed import of `ridge-house-plan.md` creates the exact
Golden entities, quantities, dependency chain, and initial state without manual
data entry or unresolved conflicts.

Verification: capture the import review and confirmed project; compare every
locked field in this document.

### P-02 — Rehearse the vertical slice

Acceptance: import, field update, approval, continuation, and delivery delay
complete in the planned order with one mutation set and truthful audit state.

Verification: perform three clean rehearsals. The third must fit the timeline
without rushing narration or hiding latency.

### P-03 — Lock proof and narration

Acceptance: all visible IDs, quantities, statuses, logs, architecture labels,
and spoken claims match the exact deployed revision.

Verification: conduct one sound-off visual review and one narration-only review;
both must communicate the complete story independently.

### P-04 — Record and quality-check

Acceptance: the exported video meets every recording gate, shows the continuous
Proof of Action, contains no secret/private data, and plays publicly while
signed out.

Verification: two people or two separate review passes score the video against
the official 40/30/30 criteria before submission lock.

### P-05 — Earn available bonus points

Acceptance: publish one substantive public build article or video created for
the hackathon and one public social post with `#AllThingsAgenticHackathon`.

Verification: links are public, identify the project accurately, and are added
to the Devpost submission before the deadline. Do not bolt on another AI model
only for bonus credit unless it has a real, demonstrated product role.

## Final judge self-score

Score each row from 1 to 5. Do not publish until every row is at least 4 and
Proof of Action is 5.

| Judge question | Target | Evidence in the video |
| --- | ---: | --- |
| Is the friction immediate and real? | 5 | PM document plus one field update replacing fragmented coordination. |
| Does the agent complete high-value work, not just answer? | 5 | Multiple durable mutations, approval pause, continuation, later autonomous delay response. |
| Is the Taskmaster twist unmistakable? | 5 | “Bring the plan you already have; OG follows through when reality changes.” |
| Is model authority safely bounded? | 5 | Review before import commit, typed tools, explicit approval, truthful skipped delivery. |
| Is state robust and failure-aware? | 4+ | Firestore truth, stable IDs, replay safety, same-run continuation evidence. |
| Is Google technology substantive? | 5 | Gemini extraction/reasoning, ADK workflow, Cloud Run, Pub/Sub, Firestore, Logging/Trace. |
| Is execution undeniable? | 5 | Continuous 73-second product action with visible before/after state. |
| Is the story understandable without repository knowledge? | 5 | One project, one update, one consequence chain, one closing thesis. |

The winning discipline is subtraction: one project source, one operational
story, one uninterrupted proof, one architecture explanation, and one honest
claim for every visible result.
