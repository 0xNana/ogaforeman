# Engineering Specification

## Objective

Build a production-ready, event-driven Oga Foreman public beta that turns unstructured site updates into durable project state and completed follow-through. The codebase must preserve a strict boundary: Gemini reasons, ADK workflows coordinate, typed tools perform actions, and Firestore holds project truth. Hackathon demo fixtures do not relax production controls.

## Technology Stack

| Layer | Choice | Status |
| --- | --- | --- |
| Backend language | Python 3.12 | Accepted |
| HTTP service | FastAPI and Uvicorn | Accepted |
| Agent runtime | Google ADK 2.x | Accepted |
| Model | Gemini model selected by environment/config | Accepted; do not hard-code production model IDs |
| Validation | Pydantic 2 | Accepted |
| Primary database | Firestore in Native mode | Accepted |
| Media storage | Google Cloud Storage | Accepted |
| Event transport | Pub/Sub with Eventarc triggers | Accepted |
| Compute | Cloud Run API and worker services | Accepted |
| Frontend | Next.js, TypeScript, Tailwind CSS, accessible component primitives | Accepted |
| Server-state client | TanStack Query or Next.js server data primitives, chosen per screen | Proposed |
| Authentication | Firebase Authentication / Identity Platform with canonical Firestore users | Accepted; application composition incomplete |
| Backend tests | pytest | Accepted |
| Frontend tests | Vitest, Testing Library, Playwright | Accepted |
| Infrastructure | Terraform or documented `gcloud` scripts | Proposed; choose once in Phase 1 |

Dependency versions must be pinned through lock files before deployed environments are created. Broad lower bounds in the current `pyproject.toml` are not a release lock.

## Commands

### Commands That Work in the Current Prototype

```bash
python3 main.py --demo
uvicorn main:app --reload --port 8000
pytest -q
```

`pytest` requires the development dependencies to be installed first.

### Target Repository Commands

These commands become mandatory as the corresponding tooling is added:

```bash
uv sync --all-extras --locked
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/python main.py --demo

cd frontend
npm ci
npm run dev
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

The root README must never advertise a command that is not implemented in the repository.

## Target Project Structure

The migration should be incremental. Existing modules may move only when a task requires the new boundary.

```text
app/
  api/                 FastAPI routers, dependencies, request/response types
  agents/              ADK coordinator and reasoning specialists
  config/              Typed environment and runtime configuration
  domain/              Entity models, enums, policies, and domain errors
  infrastructure/      Firestore, Storage, Pub/Sub, auth, and notification adapters
  prompts/             Versioned prompt templates
  repositories/        Persistence interfaces and Firestore implementations
  services/            Application use cases independent of HTTP and ADK
  tools/               Typed deterministic tools exposed to agents/workflows
  workflows/           Durable workflow definitions and state models
frontend/
  app/                  Next.js route tree
  components/           Reusable domain and primitive components
  lib/                  API client, query keys, auth, formatting
  tests/                Frontend unit/integration tests
tests/
  unit/                 Pure domain, policy, and schema tests
  integration/          Repository, API, workflow, and emulator tests
  contract/             Event, tool, and HTTP compatibility tests
e2e/                    Playwright user journeys
evals/                  Versioned model/workflow evaluation datasets
scripts/                Seed, reset, local emulator, and deployment helpers
infra/                  Reproducible Google Cloud infrastructure
docs/                   Product and engineering source of truth
tasks/                  Executable plan and status checklist
```

## Code Style

Use explicit types, UTC-aware timestamps, immutable input contracts, dependency injection, and domain-specific names. HTTP handlers, ADK agents, and infrastructure adapters should be thin.

```python
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class CompleteTaskCommand:
    project_id: str
    task_id: str
    source_event_id: str
    actor_id: str
    completed_at: datetime


def complete_task(command: CompleteTaskCommand, repository: TaskRepository) -> Task:
    task = repository.require(command.project_id, command.task_id)
    return repository.save(task.complete(at=command.completed_at.astimezone(UTC)))
```

Conventions:

- Python modules and functions: `snake_case`; classes: `PascalCase`; constants: `UPPER_SNAKE_CASE`.
- TypeScript variables/functions: `camelCase`; components/types: `PascalCase`.
- IDs are opaque strings with stable prefixes such as `prj_`, `tsk_`, `evt_`, and `run_`.
- Domain status values are enums, not unchecked strings.
- Do not use mutable default arguments.
- Use timezone-aware `datetime.now(UTC)`, not `datetime.utcnow()`.
- Tool and API errors use stable machine-readable codes.
- Comments explain non-obvious intent or constraints, not line-by-line behavior.
- Prompt templates are versioned and tested like code.

## Testing Strategy

| Level | Purpose | Dependencies |
| --- | --- | --- |
| Unit | Domain invariants, policies, matching, calculations, schemas | No network, model, or cloud |
| Tool contract | Typed tool input/output, authorization, idempotency, activity emission | In-memory/fake repositories |
| Integration | Firestore/Storage/Pub/Sub adapters, API routes, workflow persistence | Local emulators or isolated test project |
| Workflow | State transitions, retries, approval pause/resume, failure paths | Fake model and deterministic adapters |
| Eval | Extraction and reasoning quality across normal/adversarial cases | Versioned model configuration |
| E2E | Mobile intake, manager approval, activity, daily brief | Full local/deployed stack |

Requirements:

- Every mutation tool has success, authorization, validation, idempotency, and activity tests.
- Every workflow has happy path, ambiguous input, duplicate event, retry, and terminal failure tests where applicable.
- External model calls are not used in ordinary unit tests.
- E2E tests may replace model, object-storage, and event-transport dependencies at
  their external boundaries. Those substitutes must not create domain state or
  decide workflow transitions: browser submissions must enter the production event
  worker and use the production repositories, coordinator, mutation, approval,
  outbox, and continuation code. Request interception or a parallel state machine
  is not evidence for workflow status.
- Persistence acceptance tests must use fresh clients against the Firestore and
  Storage emulators; reusing an in-memory store or object dictionary is not restart
  evidence. CI runs non-backing tests separately, then starts both emulators and
  executes every `backing_services` test with no conditional skip.
- Release candidates pass the thresholds in `EVALS.md` and the global definition of done below.

## Engineering Boundaries

### Multimodal Site-Update Contract

- The API persists and links verified attachment metadata before publishing a
  site-update event. The worker must reload both the `SiteUpdate` and private
  object bytes; frontend memory, blob URLs, and client-supplied transcripts are
  not processing dependencies.
- Audio transcription is derived state. Its text and source attachment IDs are
  saved on the existing `SiteUpdate` in the same transaction as a redacted
  `site_update.transcribed` activity before structured fact extraction starts.
- Retries retain the immutable submitted event payload, reuse the same
  deterministic update/run IDs, and skip audio IDs with a persisted transcript.
  A media/model failure transitions the update and run to recoverable failed
  state for the event claim retry.
- Images are sent to the configured Gemini adapter as inline bytes with their
  verified MIME types and bounded authorized project context. Model output still
  passes through fact validation, entity resolution, policy, and typed mutation
  services.
- A photo without corroborating text or transcript cannot by itself create a
  high-confidence completion mutation. Visual uncertainty must produce an
  observation/clarification and a durable waiting state.
- The aggregate inline-media limit is configurable below Gemini's request cap;
  Storage reads enforce size and SHA-256 again at consumption time.

### Always Do

- read `PRODUCT.md`, `SECURITY_SAFETY.md`, and the active task before coding;
- validate inputs at service boundaries;
- route project writes through repositories and typed tools;
- create an `ActivityEvent` in the same logical transaction as each mutation;
- make event consumers and workflow steps idempotent;
- preserve tenant/project authorization context;
- add tests before or with behavior changes;
- update contracts and docs when behavior changes.

### Ask First

- add a new core workflow or product area;
- change the database model in a backward-incompatible way;
- add a paid service or major dependency not in the accepted stack;
- change authentication strategy;
- lower a safety/approval threshold;
- expose a new public integration endpoint;
- replace Google ADK workflow primitives with custom orchestration.

### Never Do

- store project truth only in prompts, model context, process memory, or browser state;
- let model-generated text execute arbitrary database operations;
- log secrets, raw auth tokens, chain-of-thought, or unnecessary personal data;
- auto-approve purchases, external commitments, task cancellation, or safety-critical actions;
- claim structural, engineering, or safety certification;
- commit credentials or edit generated/vendor directories by hand;
- remove a failing test merely to make CI green;
- add billing, credits, subscriptions, or feature gating to V1.

## Global Definition of Done

A task is done only when:

- its acceptance criteria are met;
- relevant automated tests pass;
- lint, format, and type checks pass for touched languages;
- errors and empty/loading/retry states are handled;
- authorization, validation, idempotency, and audit behavior were considered;
- docs, API contracts, evals, and seed data are updated when affected;
- no secrets or high-risk debug output were introduced;
- `tasks/todo-v1.md` and `docs/STATUS.md` reflect the result.

A release is done only when:

- the four core workflows pass end-to-end;
- the seeded demo can be reset and repeated;
- duplicate delivery causes no duplicate mutations;
- approval pause/resume survives a process restart;
- core mobile and desktop flows pass accessibility and browser checks;
- deploy, smoke test, rollback, and operational runbooks are verified.

The release also clears every control in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). A passing happy-path demo is insufficient if restart, concurrency, duplicate delivery, authorization, approval recovery, or API-backed UI tests fail.

## Open Engineering Decisions

- Terraform versus checked-in `gcloud` scripts for infrastructure provisioning.
- Which login providers, if any, follow the initial Email/Password public-beta flow.
- Whether the first deployed V1 uses one Cloud Run image with two entrypoints or separate API/worker images.
- Exact Gemini model IDs and fallback policy after measuring eval quality, latency, and cost.
