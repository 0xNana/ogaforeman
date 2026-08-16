# OG Foreman

OG Foreman turns construction-site updates into verified project state and operational follow-through. A foreman can submit text, voice, photos, or files; OG interprets the update, resolves it against authorized project context, and coordinates tasks, blockers, material requests, approvals, reports, and notifications.

OG is an event-driven operations system, not a general-purpose chatbot.

> Gemini reasons. Google ADK workflows coordinate. Typed tools mutate. Firestore is the source of truth. Humans approve consequential actions.

## Status

This repository is a locally verified release candidate for the OG Foreman V1 public beta. The core application, authenticated API, Next.js client, durable workflow paths, emulator-backed restart tests, deployment scripts, and production-readiness controls are implemented. It is not a claim that every cloud release gate has passed.

Before a public deployment, review [docs/STATUS.md](docs/STATUS.md), [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md), and [tasks/todo-v1.md](tasks/todo-v1.md). A real environment must provide valid Gemini credentials/model access, Firebase browser authentication evidence, operational alert/trace evidence, backup verification, and human security and safety review.

## V1 scope

OG has four supported workflows:

1. **Daily Site Update** — ingest multimodal updates, extract evidence-backed facts, update safe state, create issues or requests, and refresh the report.
2. **Material Shortage** — calculate shortages, prepare a request, pause for approval when required, and track the simulated supplier lifecycle.
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
                 OgaCoordinator + ADK workflows
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
- **Google ADK** provides agent registration and workflow coordination, including fan-out/fan-in, durable checkpoints, and approval continuation.
- **Typed services/tools** enforce authorization, evidence, confidence, idempotency, safety, and version checks before every mutation.
- **Firestore** stores projects, tasks, dependencies, materials, ledger entries, issues, reports, approvals, events, runs, outbox records, and activity history.
- **Cloud Storage** stores private original media. Workers re-read and verify attachments; browser memory and client transcripts are not processing truth.
- **Pub/Sub and Cloud Run** provide at-least-once event delivery and separate API and worker execution boundaries.

Detailed contracts are indexed in [docs/README.md](docs/README.md). Accepted architectural decisions are in [docs/decisions](docs/decisions).

## Requirements

- Python 3.12
- `uv` 0.11 or newer
- Node.js 22 and npm
- Java 21 when running Firebase emulators through browser E2E
- Docker for container smoke tests
- Google Cloud credentials only for live Gemini and cloud deployment paths

## Local setup

From the repository root:

```bash
uv sync --all-extras --locked
cp .env.example .env
cd frontend
npm ci
cp .env.example .env.local
cd ..
```

The default local configuration is safe for development: fake model enabled, demo mode enabled, and no remote Firestore access. Never point local demo data at a production project.

### Deterministic rehearsal

```bash
.venv/bin/python main.py --demo
```

This runs the disposable deterministic demo path. It is useful for orientation and does not replace the production worker or cloud deployment evidence.

### API and web application

Run the backend:

```bash
.venv/bin/uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. Authenticated frontend routes use the configured versioned API and do not fall back to fixture project data when the API is unavailable.

### Firestore and Storage emulators

```bash
npx --yes firebase-tools@15.26.0 emulators:start \
  --only firestore,storage \
  --project oga-foreman-test
```

Then configure the emulator host and run relevant tests:

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
.venv/bin/python -m pytest -q tests/integration/test_firestore_repositories.py
```

Deployed environments must never set `FIRESTORE_EMULATOR_HOST`.

### Live Gemini rehearsal

Use a disposable emulator project and keep credentials in `.env`, never in source control or shell history:

```bash
USE_FAKE_MODEL=false
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL_ID=gemini-3.6-flash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085

.venv/bin/python scripts/run_live_site_update.py
```

This exercises the claimed worker path, typed mutations, durable run and approval state, duplicate suppression, and report/activity projections. Model availability, quotas, and billing are external dependencies.

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

For a clean-worktree reproducible matrix:

```bash
.venv/bin/python scripts/run_clean_checkout_matrix.py
```

For backing-service durability, use fresh Firestore and Storage clients around approval pause and continuation. An in-memory repository or conditional test skip is not restart evidence.

## Configuration and deployment

Runtime configuration is owned by `app.config.Settings`. Deployed preview, staging, and production environments require Google Cloud, Firestore, Storage, Pub/Sub, Gemini, authentication, CORS, and signed-proposal configuration. Fake model and demo modes are rejected in production.

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
- Approval decisions are persisted, version-checked, and resume the original run after restart.
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
tasks/        executable plan and evidence-based V1 checklist
```

## Development rules

Read the required contracts before changing code:

1. [Product](docs/PRODUCT.md)
2. [Engineering specification](docs/ENGINEERING_SPEC.md)
3. [Production readiness](docs/PRODUCTION_READINESS.md)
4. The active section of [tasks/plan.md](tasks/plan.md)
5. [V1 checklist](tasks/todo-v1.md)

Keep the four-workflow scope locked. Add tests and evaluation cases for behavior changes, update [docs/STATUS.md](docs/STATUS.md) and the checklist at phase boundaries, and record expensive-to-reverse decisions as ADRs. Do not add billing, subscriptions, credits, payments, or unrelated construction-management scope.

## Data and redistribution

Review the repository and dependency licenses before redistribution. Do not commit credentials, production exports, private media, personal data, or unredacted model traces. Configure retention and access policies for any real project data before using a non-disposable environment.
