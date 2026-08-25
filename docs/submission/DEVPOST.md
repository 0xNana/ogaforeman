# Devpost Submission Copy

This copy is written for the public Devpost entry. A fake model, deterministic
`/demo`, logging notifier, dirty-source artifact, or old Cloud Run revision is
not live submission evidence.

## Project details

**Project name:** OG Foreman

**Category:** Taskmaster

**Tagline:** Construction updates in. Authorized operational follow-through out.

**Hosted application:** https://ogaforeman-cloud-2026.web.app/

**Source repository:** https://github.com/0xNana/ogaforeman

**Devpost project URL:** `TODO: add the public Devpost project URL after publishing`

**Public demo video:** `TODO: add the public YouTube or Vimeo URL; maximum four minutes`

**Support contact:** `TODO: add the monitored entrant email in Devpost`

**Testing access:** No private credentials are required. Judges can create a
free account and initialize their own synthetic project through the hosted app.

**Architecture diagram:**
[`docs/submission/architecture-diagram.svg`](architecture-diagram.svg)

**Architecture source:**
[`docs/submission/architecture-diagram.mmd`](architecture-diagram.mmd)

**Production agent inventory:**
[`docs/submission/AGENT_INVENTORY.md`](AGENT_INVENTORY.md)

**Judge testing instructions:** [`docs/submission/TESTING.md`](TESTING.md)

## Operational Utility - 40%

### Inspiration

Construction work rarely arrives as clean software input. A foreman reports
what changed in a voice note, photo, or short message, while the operational
consequences span tasks, dependencies, inventory, material requests, approvals,
daily reporting, and follow-up. The friction is not producing another summary;
it is carrying trustworthy state across all those steps without losing human
authority.

The product was shaped around the practical friction of turning terse field
updates into coordinated, authorized work without requiring a foreman to
re-enter the same facts across several tools.

### Product

OG Foreman is a production SaaS foundation for that coordination gap. It has a
multi-tenant authenticated web application, versioned API, durable event
transport, private background worker, Firestore persistence, human approval,
audit history, and reviewed Google Cloud deployment path. It is not a scripted
animation and not a chatbot that only drafts text.

OG supports four bounded workflows:

1. **Daily Site Update:** interpret authorized text, voice, and photo evidence;
   resolve canonical project entities; update safe task, blocker, inventory,
   request, and Daily Log state.
2. **Material Shortage:** compute the exact shortage from persisted requirements
   and inventory, prepare a request, and pause before a purchase or commitment.
3. **Blocker and Delay:** assess affected tasks and dependencies, update risk,
   create follow-up, and coordinate the demonstrated external notification.
4. **Daily Brief:** assemble persisted progress, blockers, risks, approvals,
   overdue work, and next focus.

### Golden Scenario

The project manager first uploads the canonical Ridge House plan already used
by the team. Direct Gemini structured extraction produces a typed draft;
deterministic validation and human review precede one typed Firestore commit.
The confirmed project contains First-floor blockwork, Electrical rough-in,
First-floor plastering, their dependency relationships, Cement Bags with 25 on
hand, and a linked 100-bag plastering requirement. The foreman then submits:

```text
First-floor blockwork is complete. The electrician did not come today. We have
10 bags of cement left. Plastering starts tomorrow.
```

The update changes stock from 25 to 10 bags. One authenticated update enters
the production event boundary. The Daily Site Update ADK workflow interprets
the evidence, resolves canonical entities, fans
out progress/blocker/material analysis, completes blockwork, leaves electrical
progress unchanged, creates the absence blocker and follow-up, records the 10
bags, computes the 90-bag shortage, prepares the request, refreshes the Daily
Log, and pauses at approval. No purchase or supplier commitment is made before
the human decision.

After approval, the same logical ADK execution continues through the guarded
typed action. Later, an authenticated operator reports the supplier delay for
the canonical material request. Nobody prompts OG in chat: the dedicated
Delivery Delay ADK workflow retrieves the request, material, directly affected
tasks, and downstream dependencies; marks the request delayed; updates risk;
creates follow-up; and uses a durable outbox to persist one external-delivery
outcome before its notification node completes. Temporary staging records that
outcome as explicitly skipped; production retains Google Chat delivery.

The value shown is operational state change: one field update becomes linked,
auditable work across the project instead of a message someone must manually
re-enter in several places.

No time-saved metric is claimed; the demonstrated value is the linked,
auditable state change and follow-through.

## Architectural Discipline - 30%

### Authority split

**Gemini reasons or extracts. Google ADK coordinates agentic operations. Typed
tools and deterministic services mutate. Firestore is the source of truth.**

This claim is intentionally scoped. Project initialization calls Gemini
directly for schema-constrained extraction, then uses deterministic validation,
human review, and a transactional commit. It is not an ADK workflow, and this
submission does not claim every Gemini path uses ADK.

Production code passes four real workflow roots to ADK `Runner`:

- `daily_site_update_workflow`;
- `delivery_delay_workflow`;
- `agentic_project_conversation`;
- `project_event_workflow`, a compatibility root for remaining registered
  events.

There is no decorative specialist `LlmAgent` hierarchy. Gemini receives bounded
authorized context and typed schemas but no Firestore write tool. Typed tools
re-check authorization, canonical identity, policy, evidence, optimistic
versions, and idempotency before deterministic services mutate state.

### Durable workflow boundary

FastAPI authenticates and validates input, persists a source record, and emits a
stable `ProjectEvent`. Pub/Sub delivers at least once to a private Cloud Run
worker using authenticated push. The worker claims the event and selects the
registered ADK workflow. Firestore holds project state, claims, approvals,
outbox records, ActivityEvents, and AgentRun projections; Cloud Storage holds
verified private media.

Every domain mutation shares a transaction with its `ActivityEvent`. Stable
event IDs, idempotency keys, create-if-absent claims, deterministic
fingerprints, optimistic versions, and bounded leases make replay and
concurrency explicit rather than relying on process memory.

### Human authority

Purchases, external commitments, financial actions, task cancellation, major
schedule changes, and safety-critical actions cannot be auto-approved. The
approval boundary persists the approval and original ADK application, session,
invocation, workflow, and request identifiers before interruption. An
authenticated, version-checked decision emits a replay-safe continuation event;
the implementation responds to the original approval request and guards the
approved action against duplication.

Same-run continuation has local production-worker test coverage. Production
process-loss durability is not claimed until the final worker-replacement
rehearsal passes.

### Real external boundary

The production path contains no supplier simulator and no automatic logging
fallback. A supplier-reported delay enters through authenticated operator
intake. The reviewed staging/production configuration accepts only the Google
Chat incoming-webhook adapter. A deterministic outbox identity, persisted
claim, bounded retry, terminal status, and provider result protect the send.
Logging and in-memory providers are development/test fakes and do not count as
external coordination.

### Observability

Cloud Logging and Cloud Trace carry allowlisted request, event, run, workflow,
node, tool, outbox, provider, and status identifiers. ActivityEvent provides the
atomic domain audit trail. AgentRun is an authorized product projection of run
status and ADK identity, not the ADK execution cursor. Prompts, secrets, raw
private media, unrestricted model output, and chain-of-thought are excluded.

## Demo and Production Readiness - 30%

### What the repository implements

- Separate Next.js web, FastAPI API, and private worker services.
- Firebase authentication and layered project authorization.
- Firestore repositories and transactions rather than a production in-memory
  project database.
- Private signed Cloud Storage upload and server-side attachment verification.
- Pub/Sub claims, retry, dead-letter configuration, and replay-safe consumers.
- Explicit ADK Daily Site Update, Delivery Delay, conversation, and compatibility
  workflow roots.
- Typed mutation services, approval state, ActivityEvents, AgentRun projection,
  durable notification outbox, explicit disabled provider, and Google Chat adapter.
- Clean-source build metadata, `/api/v1/version`, Cloud Run revision/digest
  verification, and machine-readable deployment evidence generation.
- Unit, contract, workflow, integration, browser, production-readiness, and
  evaluation suites with fail-closed release wrappers.

The live operational evaluation, staging rehearsal, restart/resume proof,
external notification, deployment provenance, and repository checks are
maintained as release evidence for the submitted revision. Fixture evaluation
and `/demo` are orientation or regression tools, not operational proof.

### Four-minute proof plan

1. Show the hosted application and `/api/v1/version` for the submitted commit.
2. Submit the multimodal Golden update and show the live ADK run moving through
   interpretation, canonical resolution, branches, tools, and approval pause.
3. Show the human decision and native continuation of the same run after the
   rehearsed worker replacement.
4. Submit the later authenticated delivery delay and show the autonomous risk,
   follow-up, Daily Log/activity, terminal run, and explicit skipped external outcome.
5. Refresh, sign out/in, and show the same Firestore-backed state plus correlated
   Cloud Logging or Trace identifiers.

The final public video URL and timestamps are entered in the Devpost form when
the video is published.

## How we built it

- **AI and workflows:** Gemini 3.6 Flash through the Google Gen AI SDK; Google
  ADK 2.6.2 `Runner`, workflow nodes, tools, interruption, and continuation.
- **Application:** Python 3.12, FastAPI, Pydantic, Next.js 16, React 19, and
  TypeScript.
- **Google Cloud:** Cloud Run, Firestore, Cloud Storage, Pub/Sub, Cloud
  Scheduler, Cloud Build, Artifact Registry, Secret Manager, Firebase
  Authentication and Hosting, Cloud Logging, Cloud Trace, and Cloud Monitoring.
- **External destination:** one Google Chat incoming webhook for production,
  configured through Secret Manager; staging may temporarily disable delivery.

No proprietary external dataset is required. The authorized project team
provides site text, voice, photos, project documents, task/dependency data,
material requirements, inventory, and subsequent delivery information. The
submission scenario must use synthetic entrant-owned data and media.

## Challenges and learnings

The hardest boundary was model authority. Construction language is ambiguous,
negation matters, and a fluent interpretation is not permission to mutate.
Typed model output, deterministic canonical resolution, and typed tools made
the boundary testable.

Approval was a distributed-systems problem rather than a UI button. The decision
is versioned and auditable, survives process replacement, targets the exact
interrupted request, and avoids replaying prior side effects. The repository
persists both domain approval state and ADK execution identity.

At-least-once event and notification delivery also changed the design. Stable
identities, transactions, persisted claims, and outbox state matter as much as
the prompt. A credible agent demo must show those state transitions and cloud
execution, not only polished prose.

## Submission compliance

- English is supported by the product and submission materials.
- Judge access must remain free through October 1, 2026.
- The public video must be on YouTube or Vimeo, no longer than four minutes, and
  visibly prove the submitted Google Cloud execution.
- Team, eligibility, ownership, consent, conflict, and third-party asset
  disclosures are completed in the Devpost form.
- Official rules: https://allthingsagentichackathon.devpost.com/rules

## Optional bonus links

**Public build article or podcast:** `TODO (optional): add a public URL and state that it was created for this hackathon`

**Social post:** `TODO (optional): add the public URL using #AllThingsAgenticHackathon`

**Additional Google AI models:** None claimed.
