# OG Foreman

OG Foreman turns messy construction-site evidence into authorized, durable project updates and operational follow-through.

## What it does

OG is an event-driven SaaS foundation for construction coordination, not a
general-purpose chatbot and not a simulated project dashboard. It provides a
multi-tenant authenticated web application, versioned API, durable project
state, background workflows, approvals, audit history, and deployment controls.

Project initialization accepts supported schedule, scope, and material sources.
Gemini produces a schema-constrained draft; deterministic validation and human
review precede the transactional Firestore commit. Project initialization is
not an ADK workflow.

Once a project exists, OG supports four bounded V1 workflows:

1. **Daily Site Update:** interpret authorized text, voice, and photo evidence;
   resolve canonical tasks and materials; update safe progress, blockers,
   inventory, requests, and the Daily Log.
2. **Material Shortage:** calculate a shortage from persisted requirements and
   inventory, prepare a material request, and pause at the purchase-approval
   boundary without placing an order.
3. **Blocker and Delay:** assess affected work and dependencies, update risk,
   create follow-up, and notify a configured external destination for the
   demonstrated delivery-delay path.
4. **Daily Brief:** assemble persisted progress, blockers, material risks,
   approvals, overdue work, and next focus into a scheduled project summary.

## The problem

A short field update often implies many separate coordination tasks. Someone
must identify the work referenced, distinguish progress from negation, update
inventory, calculate shortages, link blockers to dependencies, request the
right decision, refresh the daily report, and notify the right person. When
those steps happen across calls, chats, and spreadsheets, project state drifts
away from the site.

OG closes that gap while keeping authority explicit. Safe, reversible changes
can proceed automatically. Purchases, external commitments, financial actions,
task cancellation, major schedule changes, and safety-critical actions require
a human decision.

## See OG in action

A project manager starts by uploading the project plan. OG proposes the tasks,
dependencies, and material needs it finds, and the manager reviews them before
they become the working project. On site, the foreman can then send a text or
voice update such as:

```text
First-floor blockwork is complete. The electrician did not come today. We have
10 bags of cement left. Plastering starts tomorrow.
```

From that one update, OG:

1. marks First-floor blockwork complete;
2. records the electrician's absence as a blocker without inventing progress;
3. updates cement stock to 10 bags;
4. sees that plastering needs 100 bags and identifies the 90-bag shortfall;
5. prepares a material request and asks the manager to approve it;
6. updates the Daily Log and activity history so the whole team can see what changed.

OG stops at the decision that matters. It does not place an order or claim that
a supplier has accepted one. When the manager approves the request, OG continues
the paused work without asking the team to submit the update again. If the
delivery is later reported as delayed, OG flags the affected schedule, creates a
follow-up, and records whether the external alert was delivered.

The result is the product promise in one flow: the foreman reports what happened,
OG handles the coordination, and the manager keeps control of consequential
decisions. The demo uses the same saved project records and product screens the
team uses—it is not a scripted animation. Replaying the same update does not
create duplicate tasks, requests, or actions.

For readers who want the technical design and reliability controls, see the
[submission architecture](docs/submission/ARCHITECTURE.md) and
[engineering specification](docs/ENGINEERING_SPEC.md).

## How autonomy works

OG uses a narrow authority split:

- **Gemini** performs bounded structured extraction or grounded reasoning over
  authorized context. It cannot write Firestore.
- **Google ADK** coordinates the production workflows that require agentic
  sequencing, branching, interruption, and continuation.
- **Typed tools and deterministic domain services** enforce authorization,
  canonical identity, validation, policy, optimistic versions, idempotency, and
  mutations.
- **Firestore** is domain truth. Process memory, browser state, model context,
  and `AgentRun` are not execution truth.

Production code passes four real workflow roots to ADK `Runner`:

- `daily_site_update_workflow`;
- `delivery_delay_workflow`;
- `agentic_project_conversation`;
- `project_event_workflow`, a single compatibility root for remaining
  registered events.

There is no decorative specialist-agent graph. Direct Gemini project import is
deliberately outside ADK, so this repository does not claim that every Gemini
interaction uses ADK.

## Architecture

```text
Next.js PWA / authenticated integration
                  |
                  v
             FastAPI API
                  |
        persisted ProjectEvent
                  |
                  v
 Pub/Sub -> private Cloud Run worker -> Google ADK Runner
                                           |
                      +--------------------+--------------------+
                      |                    |                    |
                Gemini reasoning     typed tools         approval pause
                      |                    |                    |
                      +---------- deterministic services ------+
                                           |
                                           v
                                      Cloud Firestore
                                           |
                            ActivityEvent + AgentRun views
```

Private media is uploaded to Cloud Storage and verified before worker/model
use. Delivery notifications use a persisted outbox, an explicit disabled mode,
and one Google Chat adapter.
Cloud Logging and Cloud Trace correlate allowlisted request, event, run,
workflow, node, tool, and provider identifiers without prompts, secrets, or
chain-of-thought.

- [Submission architecture explanation](docs/submission/ARCHITECTURE.md)
- [Mermaid source](docs/submission/architecture-diagram.mmd)
- [Submission SVG](docs/submission/architecture-diagram.svg)
- [Production agent inventory](docs/submission/AGENT_INVENTORY.md)
- [Engineering architecture contract](docs/ARCHITECTURE.md)

## Google technology

Only the following Google technologies are used by the implementation and
deployment configuration:

- **Gemini 3.6 Flash** through the Google Gen AI SDK; deployed model calls use
  the configured Vertex AI backend.
- **Google Agent Development Kit 2.6.2** for registered workflow roots,
  `Runner`, workflow nodes, tools, interruption, and continuation.
- **Cloud Run** for separate web, API, and private worker services.
- **Cloud Firestore** for projects, membership, tasks, dependencies, material
  state, approvals, events, claims, reports, outbox, ActivityEvents, and
  AgentRuns.
- **Cloud Storage** for private verified media.
- **Pub/Sub** for authenticated asynchronous delivery, retry, and dead letters.
- **Cloud Scheduler** for configured daily-brief delivery.
- **Google Chat incoming webhook** as the implemented production
  external-notification destination; preview/staging may explicitly disable it.
- **Firebase Authentication and Hosting** for browser identity and hosted entry.
- **Cloud Build and Artifact Registry** for container builds and images.
- **Secret Manager** for deployed signing and Google Chat credentials.
- **Cloud Logging, Trace, and Monitoring** for correlated telemetry and alerts.

## Human-in-the-loop

Consequential actions create a versioned approval linked to the material
request and original run. The workflow persists its ADK application, session,
invocation, workflow, and request identity before reporting
`waiting_for_approval`. An authenticated approver resolves the exact version;
the decision is persisted and published as a replay-safe continuation event.

The implementation responds to the original ADK approval request and guards the
approved action against replay. The restart rehearsal preserves the same
logical session, invocation, workflow, and AgentRun, then executes the approved
action once.

## Reliability

- **Durable state:** Firestore repositories and transactions own project state,
  event claims, approvals, outbox items, ActivityEvents, and AgentRun
  projections. Cloud Storage owns original media. No production path uses an
  in-process project database.
- **Idempotency:** stable event IDs, API idempotency keys, persisted claims,
  deterministic entity fingerprints, typed-tool guards, and notification
  deduplication keys protect at-least-once delivery and replay.
- **Restart and resume:** approval state and ADK identifiers are persisted;
  continuation targets the original logical request. The ADK resumability API
  is experimental and pinned.
- **Concurrency:** Firestore transactions, create-if-absent claims, optimistic
  version checks, and bounded claim leases prevent silent last-write-wins and
  expose conflicts for retry or review.
- **External failure isolation:** Google Chat delivery occurs outside the domain
  transaction through a durable outbox. Failure remains visible, and explicit
  staging disablement is persisted as skipped, without rolling back valid
  project mutations or falsely reporting a send.

## Evaluation

Project-import extraction and live site coordination are separate evaluation
surfaces. Passing import cases cannot compensate for a failing operational run.

The Golden operational gate requires all eight checks and canonical entity
resolution accuracy of `1.0`:

1. blockwork completion;
2. electrical blocker without false progress;
3. cement inventory;
4. 100-bag cement requirement;
5. 90-bag shortage;
6. material request;
7. pending approval with no premature commitment;
8. later delivery-delay reaction.

Fixture evaluation is deterministic regression evidence only:

```bash
.venv/bin/python scripts/run_evals.py --adapter fixture
.venv/bin/python scripts/run_golden_evals.py --adapter fixture
```

The release evaluation uses billed Vertex execution from a clean commit:

```bash
.venv/bin/python scripts/run_golden_evals.py \
  --adapter gemini \
  --backend vertex \
  --output artifacts/evals/golden-live-gemini.json
```

An artifact with `source_tree_dirty: true`, a mismatched Git SHA, skipped
backing services, or a non-Vertex backend is not release evidence. Live scores
are recorded in the generated evaluation artifact for the submitted revision.

## Run locally

### Requirements

- Git;
- Python 3.12.x and `uv` 0.11 or newer;
- Node.js 22.x and npm;
- Java 21 for Firebase emulators and browser E2E;
- Docker only for container verification;
- Google credentials only for live Gemini or cloud paths.

### Install

```bash
git clone https://github.com/0xNana/ogaforeman.git
cd ogaforeman
uv sync --all-extras --locked
npm --prefix frontend ci
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

The lockfiles are authoritative. Keep credentials in the ignored environment
files and never point local demo/emulator configuration at a production project.

### Deterministic orientation

```bash
.venv/bin/python main.py --demo
```

This command exits after an in-memory rehearsal. It does not start the product,
call live Gemini, exercise Google Cloud, or prove external coordination.

### Authenticated local stack

Terminal 1:

```bash
npx --yes firebase-tools@15.26.0 emulators:start \
  --only auth,firestore,storage \
  --project oga-foreman-local
```

Terminal 2:

```bash
.venv/bin/uvicorn main:app --reload --port 8000
```

Terminal 3:

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:3000`. Populate the blank Firebase web fields in
`frontend/.env.local` and set
`NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_URL=http://127.0.0.1:9099`. The root `.env`
already points Firestore at `127.0.0.1:8086`; deployed environments must never
set an emulator host.

The reviewed fully seeded authenticated local path is the Playwright stack:

```bash
cd frontend
npm run test:e2e
```

### Live Gemini with disposable local state

Set `USE_FAKE_MODEL=false`, a valid `GEMINI_API_KEY`,
`GEMINI_MODEL_ID=gemini-3.6-flash`, and the Firestore emulator host in the
ignored `.env`, then run:

```bash
.venv/bin/python scripts/run_live_site_update.py
```

This uses real Gemini with emulator state; it is not Vertex or Cloud Run proof.

## Deploy

Deployment prerequisites and IAM details are documented in
[infra/README.md](infra/README.md) and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
Staging and production require Vertex model configuration, Firestore, Storage,
Pub/Sub, Firebase identity, authorized origins, a durable ADK session backend,
and Secret Manager values. Staging may set `NOTIFICATION_PROVIDER=disabled`;
production requires `NOTIFICATION_PROVIDER=google_chat` and its webhook secret.

Verify that the configured numeric Agent Engine ID resolves in the selected
Google Cloud project and region:

```bash
./infra/check-config.sh
```

Verify native ADK approval interruption and same-session continuation through
the configured Vertex Agent Engine session backend:

```bash
./infra/check-runtime.sh
```

Review commands without cloud mutation:

```bash
DEPLOY_DRY_RUN=true ./infra/deploy.sh
```

Deploy a clean committed staging revision:

```bash
DEPLOY_ENVIRONMENT=staging ./infra/deploy.sh
```

The deployment derives the full Git SHA, application version, UTC build time,
and dirty-tree state; stamps the images and Cloud Run revisions; and fails if
`/api/v1/version`, repository `HEAD`, latest ready revisions, or resolved image
digests disagree. Passing evidence is written to the ignored
`artifacts/operations/staging-deployment-current.json`; do not commit that file.

The deployed revision is verified through `/api/v1/version`, Cloud Run revision
metadata, image digests, and correlated Cloud Logging/Trace identifiers.

## Testing

Backend gates:

```bash
uv sync --all-extras --locked
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/production_readiness
.venv/bin/python scripts/check_docs.py
```

Frontend gates:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Approval restart gate, with both emulator endpoints configured:

```bash
.venv/bin/python scripts/run_adk_resume_gate.py
```

That wrapper fails when Firestore or Storage endpoints are absent; a skipped
test is not a pass. The reproducible release procedure is in
[submission testing instructions](docs/submission/TESTING.md).

## Repository structure

```text
app/                       API, domain, ADK workflows, services, tools, persistence
frontend/                  Next.js product UI and browser tests
tests/                     unit, contract, integration, workflow, readiness tests
evals/                     versioned extraction and conversation datasets
infra/                     Google Cloud deployment, monitoring, rollback
scripts/                   evaluation, smoke, backup, repair, evidence tooling
docs/                      product, architecture, API, security, operations
docs/submission/           Devpost copy, architecture, demo, and testing
```
