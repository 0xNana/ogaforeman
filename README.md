# Oga Foreman

Tell Oga what happened. Oga handles the follow-through.

Oga Foreman is an autonomous construction-site coordinator for voice notes,
photos, short messages, and operational events. The product target is simple:
turn messy site updates into verified progress, blockers, material requests,
reports, approvals, and follow-ups without becoming another dense dashboard.

## Current release status

The repository contains a substantial V1 implementation and the Phase 8 release
tooling, but it is **not production-ready yet**. All 13 local
production-readiness controls pass. The site-update API now persists intake and
outbox state, while the claimed worker routes through `OgaCoordinator`, executes
the Daily Site Update through an ADK custom agent, and applies typed authorized
mutations. The canonical mixed update now persists task progress, blockers and delay risk,
material stock and its approval-gated request, the daily report, activity, and
run state through `/api/v1`. Remaining blockers are live Gemini evaluation,
real Firebase browser evidence, and staging operations.

Staging deployment, rollback, alert, trace, backup, and isolated-restore evidence
also require a real Google Cloud environment. See
[Implementation Status](docs/STATUS.md) and
[Production Readiness](docs/PRODUCTION_READINESS.md) before deploying.

Firebase token verification, canonical user resolution, role policy, and
project-scoped repository guards are implemented and tested as components. They
are now composed into the configured API alongside a Firebase browser session,
auth screens, idempotent user bootstrap, and project onboarding. Real Firebase
browser/staging evidence is still outstanding. See the
[authentication contract](docs/AUTH.md) for the exact boundary and remaining
work.

## Architecture boundary

```text
site update / schedule / supplier event
                  |
                  v
       versioned ProjectEvent + Pub/Sub
                  |
                  v
      authenticated Cloud Run worker
                  |
                  v
        OgaCoordinator + workflows
                  |
       typed, authorized mutation tools
                  |
                  v
 Firestore domain state + atomic ActivityEvent
```

- Gemini interprets bounded site context.
- Google ADK coordinates the four V1 workflows.
- Typed services and tools perform mutations.
- Firestore is the deployed source of truth.
- Consequential actions return to a human for approval.

The four V1 workflows remain: Daily Site Update, Material Shortage, Blocker and
Delay, and Daily Brief.

## Quick start

Requirements: Python 3.12, `uv` 0.11+, and Node.js 22.

```bash
UV_CACHE_DIR=/tmp/oga-uv-cache uv sync --all-extras --locked
cp .env.example .env
cd frontend
npm ci
cp .env.example .env.local
```

Run the deterministic three-pass local rehearsal:

```bash
.venv/bin/python main.py --demo
```

Start the Firebase emulators in a separate terminal:

```bash
npx --yes firebase-tools@15.26.0 emulators:start --project demo-oga-foreman
```

Run a live Gemini call against real typed tools and the Firestore emulator:

```bash
# Set these in .env; do not paste the API key into a shell history command.
USE_FAKE_MODEL=false
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL_ID=your-enabled-gemini-model
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085

.venv/bin/python scripts/run_live_site_update.py
```

This guarded command resets only the disposable demo project, persists intake
and outbox state, calls Gemini through the configured Developer API key or
Gemini Enterprise Agent Platform ADC path inside the worker's ADK runtime,
and fails unless task, issue, material ledger, request, approval, report,
activity, source-update, and paused-run state persist in the emulator. Pub/Sub
transport is delivered in-process;
the claimed worker execution path is the same path used by the HTTP push handler.

The rehearsal covers approval, rejection, duplicate delivery, a reconstructed
report projection, a simulated delivery delay, and a new workflow service
instance. Its output deliberately keeps `release_blocked: true` while the
remaining workflow and external-environment evidence is incomplete.

Run the API and frontend in separate terminals:

```bash
.venv/bin/uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```

Authenticated frontend routes always use the configured API and never fall back
to fixture project data. `NEXT_PUBLIC_API_BASE_URL` is required; missing or
unavailable API configuration fails visibly.

## Verification

Backend:

```bash
UV_CACHE_DIR=/tmp/oga-uv-cache uv sync --all-extras --locked
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/production_readiness
.venv/bin/python scripts/run_evals.py --adapter fixture
.venv/bin/python scripts/run_capacity_baseline.py
.venv/bin/python scripts/check_docs.py
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

`npm run test:e2e` is self-contained: Playwright starts the pinned Firebase Auth
emulator, a seeded local FastAPI service using the real `/api/v1` routers and
approval, signed-upload, attachment-verification, site-intake, and run-status
services, plus the production Next.js build. It requires no Firebase project,
cloud credentials, API keys, or pre-set environment variables.

Re-run the complete documented matrix from an isolated tracked/non-ignored
source copy and refresh its evidence artifact with:

```bash
.venv/bin/python scripts/run_clean_checkout_matrix.py
```

Firestore integration tests require the emulator:

```bash
npx --yes firebase-tools@15.26.0 emulators:start --only firestore --project oga-foreman-test
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
.venv/bin/python -m pytest -q tests/integration/test_firestore_repositories.py
.venv/bin/python scripts/run_demo.py --mode emulator --runs 3
```

## Reliability and operations

- [Capacity evidence](artifacts/reliability/local-capacity.json) covers the local
  state-integrity envelope from `docs/SLOS.md`.
- [Backup dry run](artifacts/reliability/backup-verification-dry-run.json) records
  planned read-only cloud checks without claiming backup success.
- [Demo dry run](artifacts/reliability/demo-dry-run.json) records three
  deterministic rehearsals and the remaining blockers.
- [Infrastructure](infra/README.md) documents the separate API/worker Cloud Run
  deployment, IAM, Pub/Sub dead letters, backups, monitoring, and rollback.

## Repository map

```text
app/            domain, repositories, services, agents, workflows, API, worker
frontend/       Next.js landing page and product UI
evals/          locked structured-evaluation dataset
infra/          reviewed gcloud deployment, monitoring, and rollback scripts
scripts/        seed/reset, eval, demo, smoke, backup, capacity, repair tools
tests/          unit, contract, integration, workflow, readiness, and load suites
docs/           product, engineering, operations, and architecture contracts
tasks/          execution plan and evidence-based status checklists
```

Start with the [documentation index](docs/README.md), then read
[Product](docs/PRODUCT.md), [Engineering](docs/ENGINEERING_SPEC.md), and the
[authentication contract](docs/AUTH.md), followed by the
[current task plan](tasks/plan.md).
