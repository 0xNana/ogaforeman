# OG Foreman

OG Foreman turns construction-site updates into verified project state and operational follow-through. A foreman can submit text, voice, photos, or files; OG interprets the update, resolves it against authorized project context, and coordinates tasks, blockers, material requests, approvals, reports, and notifications.

OG is an event-driven operations system, not a general-purpose chatbot.

> Gemini reasons or performs bounded extraction. Google ADK coordinates agentic workflows. Typed tools mutate. Application services own deterministic ingestion. Firestore is the source of truth. Humans approve consequential actions.

## Status

This repository is a locally verified release candidate for the OG Foreman V1 public beta. The core application, authenticated API, Next.js client, durable workflow paths, emulator-backed restart tests, deployment scripts, and production-readiness controls are implemented. It is not a claim that every cloud release gate has passed.

Before a public deployment, review [internal-docs/STATUS.md](internal-docs/STATUS.md), [internal-docs/PRODUCTION_READINESS.md](internal-docs/PRODUCTION_READINESS.md), and [tasks/todo-v1.md](tasks/todo-v1.md). A real environment must provide valid Gemini credentials/model access, Firebase browser authentication evidence, operational alert/trace evidence, backup verification, and human security and safety review.

## V1 scope

OG has four supported workflows:

1. **Daily Site Update** — ingest multimodal updates, extract evidence-backed facts, update safe state, create issues or requests, and refresh the report.
2. **Material Shortage** — calculate shortages, prepare a request, pause for approval when required, and track authenticated delivery updates.
3. **Blocker and Delay** — resolve affected tasks and dependencies, record delay impact, assign follow-up work, and escalate safety-critical conditions.
4. **Daily Brief** — produce a scheduled summary of progress, blockers, risks, approvals, overdue work, and next focus.

Purchases, external commitments, financial actions, task cancellation, major schedule changes, and safety-critical actions are never auto-approved. OG does not send money or create binding supplier orders in V1.

## Architecture

```text
Web/PWA or integration
        |
        v
   FastAPI /api/v1
        |
   authenticated ProjectEvent
        |
        v
 Pub/Sub -> authenticated Cloud Run worker
                         |
                         v
                  named ADK workflow root
                         |
                         v
              typed services and mutation tools
                         |
       +-----------------+------------------+
       |                                    |
       v                                    v
 Firestore domain truth             Cloud Storage media
 + atomic ActivityEvents             + verified signed access
```

- **Gemini** performs bounded interpretation through the configured model adapter. Model output never writes domain state directly.
- **Google ADK** runs four named workflow roots, including fan-out/fan-in, durable checkpoints, and approval continuation. The repository does not construct an unused specialist-agent graph.
- **Typed services/tools** enforce authorization, evidence, confidence, idempotency, safety, and version checks before every mutation.
- **Firestore** stores projects, tasks, dependencies, materials, ledger entries, issues, reports, approvals, events, runs, outbox records, and activity history.
- **Cloud Storage** stores private original media. Workers re-read and verify attachments; browser memory and client transcripts are not processing truth.
- **Pub/Sub and Cloud Run** provide at-least-once event delivery and separate API and worker execution boundaries.

ADK owns OG's autonomous construction workflows and agentic project
conversation. Gemini reasons over authorized context, typed tools enforce and
apply mutations, and Firestore remains the source of truth. This is a scoped
claim: deterministic ingestion and project import are application services,
not agent workflows.

Detailed contracts are indexed in [docs/README.md](docs/README.md). Accepted architectural decisions are in [docs/decisions](docs/decisions).
The hackathon system view is available as an
[architecture diagram](docs/submission/architecture-diagram.svg) with a
[component walkthrough](docs/submission/ARCHITECTURE.md) and a
[production agent inventory](docs/submission/AGENT_INVENTORY.md).

## Reproducible setup

### Requirements

- Git
- Python 3.12.x; Python 3.13 is intentionally unsupported
- `uv` 0.11 or newer
- Node.js 22.x and npm
- Java 21 for Firebase emulators and browser E2E
- Docker only for container smoke tests or cloud-image verification
- Google Cloud credentials only for live Gemini and cloud deployment paths

Confirm the toolchain before installing dependencies:

```bash
git --version
python3.12 --version
uv --version
node --version
npm --version
java -version
```

### 1. Clone and install

Use a clean checkout so the lockfiles define the dependency graph:

```bash
git clone https://github.com/0xNana/ogaforeman.git
cd ogaforeman
uv sync --all-extras --locked
npm --prefix frontend ci
```

`uv sync --all-extras --locked` creates `.venv` from `uv.lock`. `npm ci`
installs the exact frontend graph from `frontend/package-lock.json`; do not
replace either command with an unlocked install when reproducing a release.

### 2. Create local configuration

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

The checked-in examples default to local mode, fake model, demo mode, and the
Firestore emulator at `127.0.0.1:8086`. Blank cloud and Firebase values are
intentional. Keep secrets only in the ignored `.env` files. Never point demo or
emulator data at a production project.

### 3. Run the deterministic path

This is the smallest reproducible execution. It requires no server, browser,
Google Cloud account, Firebase project, or model credential:

```bash
.venv/bin/python main.py --demo
```

The command exits after printing a structured rehearsal result. It seeds a
disposable in-memory project, exercises the bounded four-workflow behavior, and
does not read or write a remote database. It is useful for code review but does
not prove live Gemini or Google Cloud execution.

### 4. Run the complete local browser verification

The most reproducible authenticated local product path is the Playwright stack.
It starts isolated Auth and Firestore emulators, the real test API, and a
production-built Next.js app, seeds synthetic identities and project state, runs
desktop and mobile scenarios, then tears the processes down:

```bash
cd frontend
npm run test:e2e
```

Java 21 and a Chromium-compatible Playwright browser are required. If browser
binaries are not installed, install the pinned runner once with:

```bash
cd frontend
npx playwright install chromium
```

No production credentials or data are used by this path.

### 5. Run the API and web development servers

Start the configured backing services first. For Firestore and Storage work,
run this in terminal 1:

```bash
npx --yes firebase-tools@15.26.0 emulators:start \
  --only auth,firestore,storage \
  --project oga-foreman-local
```

Run the backend in terminal 2:

```bash
.venv/bin/uvicorn main:app --reload --port 8000
```

Verify its public probes:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Run the frontend in terminal 3:

```bash
cd frontend
npm run dev
```

Open http://127.0.0.1:3000. `frontend/.env.local` already points
`NEXT_PUBLIC_API_BASE_URL` at port 8000, but an interactive sign-in also needs
all blank `NEXT_PUBLIC_FIREBASE_*` fields filled with an authorized disposable
Firebase web-app configuration. Set
`NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_URL=http://127.0.0.1:9099` when using the
local Auth emulator.

The standard `main:app` fails protected routes closed unless backend identity
configuration is present. For an entirely local authenticated application with
seeded identities, use the Playwright path above; its reviewed test runner
provides the matching emulator token verifier and API configuration. The
frontend never falls back to fixture project data when the API is unavailable.

### Focused Firestore integration

```bash
npx --yes firebase-tools@15.26.0 emulators:start \
  --only firestore,storage \
  --project oga-foreman-test
```

Then configure the emulator host and run relevant tests:

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8086
.venv/bin/python -m pytest -q tests/integration/test_firestore_repositories.py
```

Deployed environments must never set `FIRESTORE_EMULATOR_HOST`.

### Live Gemini with local durable state

Use a disposable emulator project and keep credentials in `.env`, never in
source control or shell history. Set these values in the ignored root `.env`:

```dotenv
USE_FAKE_MODEL=false
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL_ID=gemini-3.6-flash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8086
```

Then, while the Firestore emulator is running, execute:

```bash
.venv/bin/python scripts/run_live_site_update.py
```

This path exercises real Gemini against disposable Firestore emulator state; it
is not proof of Vertex AI or Cloud Run execution. Model availability, quotas,
and billing are external dependencies.

### Real Google Chat notification check

Google Chat is the only production external-notification provider. Create one
incoming webhook for the dedicated synthetic demo space and place its complete
URL in `GOOGLE_CHAT_WEBHOOK_URL` in the ignored `.env`, or in Secret Manager for
a deployed environment. Set `NOTIFICATION_PROVIDER=google_chat` for the live
path. `PUBLIC_APP_BASE_URL` must be the exact HTTPS origin
used to construct safe project links. Preview, staging, and production reject
missing values at startup and report `external_notification` in readiness; they
never fall back to a logger or in-memory fake.

Local development and automated tests may explicitly use
`NOTIFICATION_PROVIDER=logging`. That provider records a deterministic bounded
event but sets `is_external=false` and never counts as external-delivery proof.

The live provider check is separately gated because it sends a visible message
to the configured real space. It refuses a dirty worktree:

```bash
.venv/bin/python scripts/run_google_chat_live_check.py \
  --confirm-send send-google-chat-live-check
```

Its ignored evidence artifact is
`artifacts/operations/google-chat-live-current.json`. It records the provider
message ID, Git commit, timestamp, and dirty-tree state without recording the
webhook or message body. Repeating it from the same commit reuses the same
provider idempotency identity for that UTC date.

## Verification

Backend quality gates:

```bash
uv sync --all-extras --locked
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/production_readiness
.venv/bin/python scripts/run_evals.py --adapter fixture
.venv/bin/python scripts/run_golden_evals.py --adapter fixture
.venv/bin/python scripts/run_capacity_baseline.py
.venv/bin/python scripts/check_docs.py
```

Frontend quality gates:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

The Playwright suite starts its own local Auth/API test stack and uses the real routers, repositories, approval service, signed-upload verification, worker, and run-status paths. Deterministic substitutes are limited to external model, storage, and transport boundaries.

The hackathon recording gate is stricter than the fixture suite. Run the billed
Vertex Golden operational evaluation and require all eight checks plus canonical
entity resolution to equal 1.0. Run it from a clean, committed tree; a live
artifact generated from uncommitted source is rejected:

```bash
.venv/bin/python scripts/run_golden_evals.py \
  --adapter gemini \
  --backend vertex \
  --output artifacts/evals/golden-live-gemini.json
```

Project-import evals are independent extraction gates and do not offset a
failing operational Golden result.

With both Firestore and Storage emulator endpoints configured, run the
fail-closed approval-resume gate. It selects the approved continuation only and
returns a nonzero status instead of accepting a skipped integration test:

```bash
.venv/bin/python scripts/run_adk_resume_gate.py
```

This gate depends on Google ADK's experimental resumability API. The repository
pins `google-adk==2.6.2`; any ADK upgrade requires this backed restart gate and
the staging worker-replacement proof to pass again.

For a clean-worktree reproducible matrix:

```bash
.venv/bin/python scripts/run_clean_checkout_matrix.py
```

For backing-service durability, use fresh Firestore and Storage clients around approval pause and continuation. An in-memory repository or conditional test skip is not restart evidence.

### Deployment provenance

Every real deployment derives the full Git SHA from a clean `HEAD`, reads the
application version from `pyproject.toml`, and stamps one UTC build time into
the backend image, frontend image, API revision, worker revision, and web
revision. The public API exposes only `git_sha`, `build_timestamp`,
`app_version`, `environment`, clean-tree state, and Cloud Run service/revision
identity:

```bash
curl "$OGA_STAGING_API_URL/api/v1/version"
```

After traffic reaches the new revisions, `infra/deploy.sh` runs a verifier that
independently derives repository `HEAD` and compares it with that response,
Cloud Run's latest ready revisions, stamped environment, and resolved image
digests. Any SHA or metadata mismatch fails deployment provenance. Passing
evidence records `repo_git_sha`, the complete version response, each service's
revision deployment timestamp, and each immutable digest. It is written to the ignored
`artifacts/operations/staging-deployment-current.json`; do not commit it, because
that would create a different Git SHA from the one it proves. See
[ADR-007](docs/decisions/ADR-007-deployment-build-provenance.md).

## Configuration and deployment

Runtime configuration is owned by `app.config.Settings`. Deployed preview,
staging, and production environments require Google Cloud, Firestore, Storage,
Pub/Sub, Gemini, Google Chat, a public application origin, authentication, CORS,
and signed-proposal configuration. Fake model and demo modes are rejected in
production.

The reviewed deployment path is documented in [infra/README.md](infra/README.md) and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Review without changing cloud state:

```bash
DEPLOY_DRY_RUN=true ./infra/deploy.sh
```

Deploy a configured staging environment:

```bash
DEPLOY_ENVIRONMENT=staging ./infra/deploy.sh
```

The deployment manages Firestore rules/indexes and deletion protection, private versioned Storage, Artifact Registry/Cloud Build, separate API and worker Cloud Run services, workload IAM, authenticated Pub/Sub push, dead letters, Scheduler, monitoring, and backup configuration. It refuses a dirty Git worktree during normal deployment so the image tag identifies reviewed source.

Verify a built container before cloud mutation:

```bash
docker build --tag oga-foreman:cloud-ready .
bash infra/smoke-container.sh oga-foreman:cloud-ready
```

Rollback moves traffic to explicitly selected, previously verified Cloud Run revisions. It does not delete or rewrite Firestore, Storage, Pub/Sub events, runs, or activities.

## Security and reliability principles

- Project authorization is enforced at API, repository, and tool boundaries.
- Every event and mutation is replay-safe and carries stable identity context.
- Every mutation atomically emits an `ActivityEvent`.
- Approval decisions are persisted and version-checked. Release requires the
  original ADK session and invocation to resume once after an actual worker
  restart; local contract tests are not production restart evidence.
- Negated or ambiguous language cannot complete tasks.
- Safety and structural hazards stop normal autonomous mutation and escalate.
- Credentials, raw media, transcripts, prompts, and hidden reasoning are not emitted in user-facing activity metadata.
- UTC-aware timestamps and bounded uploads, model inputs, retries, and rate limits are required.
- Firestore is production truth; process memory and ADK session memory are not domain persistence.

Read [docs/SECURITY_SAFETY.md](docs/SECURITY_SAFETY.md), [docs/AUTH.md](docs/AUTH.md), and [docs/SLOS.md](docs/SLOS.md) before operating the system.

## Repository map

```text
app/          domain, API, agents, workflows, services, repositories, tools
frontend/     Next.js TypeScript product UI and browser tests
tests/        unit, contract, integration, workflow, readiness, and load tests
evals/        versioned interpretation and conversation evaluation datasets
infra/        reviewed Google Cloud deployment, monitoring, and rollback scripts
scripts/      seed/reset, emulator, evaluation, smoke, backup, and repair tools
docs/         product, architecture, API, security, operations, and release contracts
docs/submission/ hackathon architecture, agent inventory, Devpost copy, demo, testing, and release gate
tasks/        executable plan and evidence-based V1 checklist
```

## Development rules

Read the required contracts before changing code:

1. [Product](docs/PRODUCT.md)
2. [Engineering specification](docs/ENGINEERING_SPEC.md)
3. [Production readiness](internal-docs/PRODUCTION_READINESS.md)
4. The active section of [tasks/plan.md](tasks/plan.md)
5. [V1 checklist](tasks/todo-v1.md)

Keep the four-workflow scope locked. Add tests and evaluation cases for behavior changes, update [internal-docs/STATUS.md](internal-docs/STATUS.md) and the checklist at phase boundaries, and record expensive-to-reverse decisions as ADRs. Do not add billing, subscriptions, credits, payments, or unrelated construction-management scope.

## Data and redistribution

Review the repository and dependency licenses before redistribution. Do not commit credentials, production exports, private media, personal data, or unredacted model traces. Configure retention and access policies for any real project data before using a non-disposable environment.
