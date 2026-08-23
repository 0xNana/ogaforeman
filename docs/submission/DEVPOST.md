# Devpost Submission Copy

> Submission owner: replace every `SUBMISSION BLOCKER` before pasting this into
> Devpost. Do not describe a deterministic demo, fake-model run, or stale cloud
> revision as live proof.

## Project details

**Project name:** OG Foreman

**Category:** Taskmaster

**Tagline:** Construction updates in. Verified operational follow-through out.

**Hosted application:** https://ogaforeman-cloud-2026.web.app/

**Source repository:** https://github.com/0xNana/ogaforeman

**Demo video:** `SUBMISSION BLOCKER: add the public YouTube or Vimeo URL`

**Architecture diagram:**
[`docs/submission/architecture-diagram.svg`](architecture-diagram.svg)

**Production agent inventory:**
[`docs/submission/AGENT_INVENTORY.md`](AGENT_INVENTORY.md)

**Testing instructions:** [`docs/submission/TESTING.md`](TESTING.md)

## Inspiration

Construction work does not fail because teams lack another chat window. It
fails in the gap between a messy field update and the many small actions needed
to keep a project truthful: resolve which task was mentioned, record progress,
surface a delay, calculate a material shortage, assign follow-up, request a
decision, refresh the daily report, and notify the right people.

OG Foreman is built for that gap. A foreman should be able to report what
happened in the natural media available on site, then trust the system to carry
out the safe operational work and ask a human only when authority or safety
requires it.

`SUBMISSION BLOCKER: entrant must add 2-4 truthful sentences explaining the
personal "Bring Your Own Friction" connection. Do not submit a generic market
story; the Taskmaster rubric explicitly asks why this problem is personal.`

## What it does

OG Foreman turns text, voice notes, photos, and project files into verified
project state and multi-step follow-through. It supports four bounded workflows:

1. **Daily Site Update:** extracts evidence-backed facts, resolves project
   entities, updates safe state, creates issues or material requests, refreshes
   the report, and records every action.
2. **Material Shortage:** computes the shortage from the material ledger,
   prepares the request, pauses when approval is required, and tracks an
   authenticated delivery lifecycle without making a purchase.
3. **Blocker and Delay:** identifies affected work and dependencies, records
   impact, creates follow-up, and escalates safety-critical conditions.
4. **Daily Brief:** assembles a scheduled summary of progress, blockers, risks,
   pending approvals, overdue work, and the next focus.

This is not a chatbot that only writes an answer. An input becomes a durable
event and an observable run. **ADK owns OG's autonomous construction workflows
and agentic project conversation. Gemini reasons over authorized context,
typed tools enforce and apply mutations, and Firestore remains the source of
truth.** Each mutation atomically adds an activity record. The Daily Site
Update exposes real context, interpretation, entity-resolution, parallel
progress/blocker/material, merge, policy, tool, approval, and continuation
nodes. Delivery delay and project conversation use dedicated ADK graphs rather
than the generic one-callback event adapter. An authenticated operator-generated
`DELIVERY_DELAYED` event cannot enter the legacy route map: its ADK workflow
loads the canonical request, material, and affected tasks, expands dependency
impact, invokes typed tools, and sends one provider-idempotent Google Chat
notification without a chat prompt. The provider outcome is durable before the
run completes.

Safe and reversible actions can run without intervention. Purchases, external
commitments, financial actions, task cancellation, major schedule changes, and
safety-critical actions cannot be auto-approved. They pause for a canonical
approver. Same-session ADK continuation is implemented and locally
contract-tested, but this draft must not claim production restart durability
until the current deployment passes the documented worker-restart gate.

## How we built it

- **AI and agents:** Gemini 3.6 Flash, Google Gen AI SDK, four named Google ADK
  workflow roots, `Runner`, typed tools, and durable Vertex AI session
  configuration. No decorative specialist `LlmAgent` graph is constructed.
- **Application:** Python 3.12, FastAPI, Pydantic, Next.js 16, React 19, and
  TypeScript.
- **Google Cloud:** Cloud Run for separate web, API, and private worker
  services; Firestore for domain truth; Cloud Storage for private evidence;
  Pub/Sub for asynchronous delivery and dead letters; Cloud Scheduler for the
  daily brief; Cloud Build and Artifact Registry for immutable images; Secret
  Manager, Firebase Authentication and Hosting, Cloud Logging, Cloud Trace,
  Cloud Monitoring, and managed backups.
- **Reliability controls:** stable event IDs, persisted delivery claims,
  optimistic version checks, idempotent tools, transactional activity events,
  persisted approval identity, guarded continuation, bounded retries, and
  correlated telemetry. Production restart durability remains a release gate.
- **Safety controls:** authorization at API, repository, and tool boundaries;
  confidence and evidence gates; fail-closed handling of ambiguous or negated
  completion claims; and explicit human control for consequential actions.

## Data sources

OG Foreman does not depend on a proprietary external dataset. It processes data
that an authorized project team supplies:

- text and voice site updates;
- project photos and documents;
- imported task schedules and material records;
- canonical project membership, aliases, tasks, dependencies, material ledger,
  approvals, and prior activity stored in Firestore.

The submission scenario uses synthetic construction data and media with no
private customer or worker information. Third-party packages are used under
their repository licenses.

## Challenges we ran into

The difficult part was not calling a model. It was defining exactly where model
authority ends. Field language is ambiguous, construction actions can be
consequential, and Pub/Sub can redeliver. We therefore made Gemini output typed
interpretations and proposals, while deterministic services own authorization,
evidence checks, idempotency, and mutation.

Approval was another systems problem rather than a UI button. A decision must
be versioned, auditable, tied to a canonical identity, and able to resume the
original workflow after a process restart without repeating earlier work.

Multimodal ingestion also required a durable boundary. The browser transcript
or preview cannot be processing truth; the worker must retrieve the verified
private object and enforce media and model-input limits.

## Accomplishments we are proud of

- One site update can produce coordinated task, blocker, material, report,
  approval, notification, and activity changes rather than a prose response.
- Every mutation is designed to be authorized, replay-safe, and paired with an
  atomic audit event.
- The approval policy allows useful autonomy without silently crossing a human
  authority or safety boundary.
- API, worker, storage, event delivery, session state, and domain state have
  explicit ownership instead of sharing process memory.
- The four-workflow boundary keeps the V1 demonstrable and testable.

## What we learned

Agent reliability comes from narrowing authority, not from writing a larger
prompt. Durable event identity and typed mutation contracts matter as much as
model quality. Human-in-the-loop design works best when the human is a precise
policy boundary, not a fallback for every step. Finally, a credible agent demo
must make state change and cloud execution visible; fluent text is not proof of
action.

## What's next

Before the contest submission, the release gate is to deploy the current commit
and capture one authenticated, live Gemini-backed workflow end to end with
correlated Cloud Run, Firestore, and logging evidence. The public
`/api/v1/version` response and generated provenance artifact must match that
submitted commit, the latest ready revisions, and their resolved image digests.
The remaining V1 work is
tracked openly in `tasks/todo-v1.md`; unfinished gates are not represented as
completed functionality.

After V1, likely extensions are real supplier integrations behind the same
approval contract, more project-file formats, additional language support, and
longer operational evaluations. Billing, payments, and unrelated project
management scope are intentionally outside this build.

## Submission compliance

- The repository history begins during the August 3-31, 2026 submission
  period. `SUBMISSION BLOCKER: entrant must disclose any pre-existing code,
  templates, assets, or other work incorporated into the project.`
- The product and all submission materials support English.
- Judge access must remain free and available through October 1, 2026.
- The public video must be no longer than four minutes and visibly prove Google
  Cloud execution.
- Official rules: https://allthingsagentichackathon.devpost.com/rules

## Optional bonus links

**Public build article or podcast:** `Optional: add URL. It must explicitly say
it was created for entry into this hackathon.`

**Social post:** `Optional: add URL using #AllThingsAgenticHackathon.`

**Additional Google AI models:** `None claimed. Do not claim a model that is
not integrated and visibly demonstrated.`
